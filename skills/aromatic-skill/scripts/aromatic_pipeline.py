#!/usr/bin/env python3
"""Prepare and run Multiwfn aromaticity workflows."""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_SKILLS = SKILL_ROOT.parent
METHOD_LIBRARY = SKILL_ROOT / "references" / "aromatic-methods.yml"
DEFAULT_SEED = 61453
ALL_TOKEN = "all"
MAGNETIC_METHODS = {"icss", "nics-zz", "nics-1d", "nics-2d"}
NICS_ALIASES = {"inics": "nics-1d", "fipc-nics": "nics-1d"}
WAVEFUNCTION_EXTS = {".fchk", ".fch", ".wfn", ".wfx", ".molden", ".mwfn", ".chk", ".gbw"}
STRUCTURE_EXTS = {".xyz", ".mol", ".sdf", ".pdb", ".mol2"}
GAUSSIAN_OUTPUT_EXTS = {".out", ".log"}
PLACEHOLDER_RE = re.compile(r"<[^>]+>")


class PipelineError(RuntimeError):
    """Recoverable pipeline failure."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multiwfn aromaticity workflow helper.")
    parser.add_argument("--aromatic", action="store_true", help="Required aromaticity task flag.")
    parser.add_argument("--explain", action="store_true", help="Write and print a method overview.")
    parser.add_argument("--method", default=ALL_TOKEN, help="Method id or comma list; use all for every method.")
    parser.add_argument("--smiles", help="SMILES string used to prepare an initial structure/input with input-skill.")
    parser.add_argument("--input", help="Structure, wavefunction, or output file for analysis.")
    parser.add_argument("--gaussian-output", help="Gaussian NMR .out/.log file used for NICS/ICSS post-processing.")
    parser.add_argument("--ring-atoms", help="Comma/range list of ring atom indices, e.g. 1-6 or 1,2,3,4,5,6.")
    parser.add_argument("--pi-orbitals", help="Comma/range list of pi orbital indices for FLU-pi/LOLIPOP.")
    parser.add_argument("--resume-manifest", help="Manifest from a previous aromatic-skill run.")
    parser.add_argument("--execute", action="store_true", help="Actually run Multiwfn when all inputs are concrete.")
    parser.add_argument("--multiwfn-bin", help="Path to Multiwfn executable.")
    parser.add_argument("--outdir", help="Explicit output directory.")
    parser.add_argument("--workdir", default=".", help="Directory where aromatic-skill-run is created.")
    parser.add_argument("--name", default="aromatic", help="Output basename.")
    parser.add_argument("--cores", type=int, default=4, help="Cores passed to input-skill when SMILES preparation is needed.")
    parser.add_argument("--memory", default="8GB", help="Memory passed to input-skill when SMILES preparation is needed.")
    parser.add_argument("--charge", type=int, help="Charge passed to input-skill when SMILES preparation is needed.")
    parser.add_argument("--multiplicity", type=int, help="Multiplicity passed to input-skill when SMILES preparation is needed.")
    parser.add_argument("--timeout", type=int, default=1800, help="External command timeout in seconds.")
    parser.add_argument("--normal-vector", help="Vector for local NICS_ZZ projection, e.g. 0,0,1.")
    parser.add_argument("--tensor", help="Nine tensor components row-wise for local NICS_ZZ projection.")
    return parser.parse_args(argv)


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug[:80] or "aromatic"


def timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def expand(path: str | Path | None) -> Path | None:
    if not path:
        return None
    return Path(path).expanduser().resolve()


def make_output_dir(args: argparse.Namespace) -> Path:
    if args.outdir:
        outdir = expand(args.outdir)
    else:
        outdir = (
            Path(args.workdir).expanduser().resolve()
            / "aromatic-skill-run"
            / f"{slugify(args.name)}-{timestamp()}"
        )
    assert outdir is not None
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def load_method_library(path: Path = METHOD_LIBRARY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def method_maps(library: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    by_id = {method["id"]: method for method in library.get("methods", [])}
    aliases: dict[str, str] = {}
    for method in library.get("methods", []):
        aliases[method["id"].lower()] = method["id"]
        for alias in method.get("aliases", []):
            aliases[alias.lower()] = method["id"]
    aliases.update(NICS_ALIASES)
    return by_id, aliases


def resolve_methods(value: str, library: dict[str, Any]) -> list[dict[str, Any]]:
    by_id, aliases = method_maps(library)
    tokens = [token.strip().lower() for token in value.split(",") if token.strip()]
    if not tokens or tokens == [ALL_TOKEN]:
        return list(library.get("methods", []))
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for token in tokens:
        method_id = aliases.get(token)
        if not method_id:
            raise PipelineError(f"Unknown aromaticity method: {token}")
        if method_id not in seen:
            resolved.append(by_id[method_id])
            seen.add(method_id)
    return resolved


def parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    result: list[int] = []
    for part in re.split(r"[,;\s]+", value.strip()):
        if not part:
            continue
        if "-" in part[1:]:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            step = 1 if end >= start else -1
            result.extend(range(start, end + step, step))
        else:
            result.append(int(part))
    return result


def format_int_list(values: list[int]) -> str:
    return ",".join(str(value) for value in values)


def parse_vector(value: str | None) -> list[float] | None:
    if not value:
        return None
    parts = [float(part) for part in re.split(r"[,;\s]+", value.strip()) if part]
    if len(parts) != 3:
        raise PipelineError("--normal-vector must contain exactly three numbers")
    norm = math.sqrt(sum(part * part for part in parts))
    if norm == 0:
        raise PipelineError("--normal-vector must not be zero")
    return [part / norm for part in parts]


def parse_tensor(value: str | None) -> list[list[float]] | None:
    if not value:
        return None
    parts = [float(part) for part in re.split(r"[,;\s]+", value.strip()) if part]
    if len(parts) != 9:
        raise PipelineError("--tensor must contain exactly nine row-wise numbers")
    return [parts[0:3], parts[3:6], parts[6:9]]


def project_tensor(tensor: list[list[float]], vector: list[float]) -> float:
    total = 0.0
    for i in range(3):
        for j in range(3):
            total += vector[i] * tensor[i][j] * vector[j]
    return total


def nics_zz_from_tensor(tensor: list[list[float]], normal: list[float]) -> float:
    return -project_tensor(tensor, normal)


def detect_file_role(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"role": "missing"}
    if not path.exists():
        return {"role": "missing", "path": str(path)}
    suffix = path.suffix.lower()
    info: dict[str, Any] = {"path": str(path), "suffix": suffix}
    if suffix in WAVEFUNCTION_EXTS:
        info["role"] = "wavefunction"
        return info
    if suffix in STRUCTURE_EXTS:
        info["role"] = "structure"
        return info
    if suffix in GAUSSIAN_OUTPUT_EXTS:
        text = read_text_prefix(path, 2_000_000)
        lower = text.lower()
        info["has_gaussian_nmr"] = "giao magnetic shielding tensor" in lower or "isotropic =" in lower
        info["has_bq"] = bool(re.search(r"\bBq\b", text))
        info["looks_nics_batch"] = bool(re.search(r"NICS\d{4}\.(out|log)$", path.name, re.I))
        info["looks_orca"] = "o   r   c   a" in lower or "orca" in lower
        info["looks_multiwfn"] = "multiwfn" in lower
        if info["has_gaussian_nmr"]:
            info["role"] = "gaussian_nmr_output"
        elif info["looks_orca"]:
            info["role"] = "orca_output"
        elif info["looks_multiwfn"]:
            info["role"] = "multiwfn_output"
        else:
            info["role"] = "output"
        return info
    info["role"] = "unknown"
    return info


def read_text_prefix(path: Path, limit: int) -> str:
    with path.open("rb") as handle:
        data = handle.read(limit)
    return data.decode("utf-8", errors="replace")


def parse_labeled_tensor_rows(lines: list[str], start: int) -> list[list[float]] | None:
    values: dict[str, float] = {}
    labels = ("XX", "YX", "ZX", "XY", "YY", "ZY", "XZ", "YZ", "ZZ")
    for line in lines[start : start + 8]:
        for label in labels:
            match = re.search(label + r"\s*=\s*([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)", line)
            if match:
                values[label] = float(match.group(1))
    if not all(label in values for label in labels):
        return None
    return [
        [values["XX"], values["YX"], values["ZX"]],
        [values["XY"], values["YY"], values["ZY"]],
        [values["XZ"], values["YZ"], values["ZZ"]],
    ]


def parse_gaussian_nmr_tensors(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    tensors: list[dict[str, Any]] = []
    iso_re = re.compile(r"Isotropic\s*=\s*([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)", re.I)
    aniso_re = re.compile(r"Anisotropy\s*=\s*([-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?)", re.I)
    for idx, line in enumerate(lines):
        iso = iso_re.search(line)
        if not iso:
            continue
        tensor = parse_labeled_tensor_rows(lines, idx + 1)
        if tensor is None:
            continue
        aniso = aniso_re.search(line)
        context = "\n".join(lines[max(0, idx - 2) : idx + 1])
        tensors.append(
            {
                "line": idx + 1,
                "isotropic": float(iso.group(1)),
                "anisotropy": float(aniso.group(1)) if aniso else None,
                "tensor": tensor,
                "is_bq": bool(re.search(r"\bBq\b", context)),
            }
        )
    return tensors


def gaussian_nics_prefix(path: Path) -> str | None:
    match = re.match(r"(.+?)\d{4}\.(out|log)$", str(path), re.I)
    if match:
        return match.group(1)
    return None


def find_batch_outputs(path: Path) -> list[str]:
    prefix = gaussian_nics_prefix(path)
    if not prefix:
        return [str(path)]
    matches = sorted(glob.glob(prefix + "[0-9][0-9][0-9][0-9].out"))
    matches.extend(sorted(glob.glob(prefix + "[0-9][0-9][0-9][0-9].log")))
    return matches or [str(path)]


def rdkit_ring_candidates(smiles: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    if not smiles:
        return [], []
    try:
        from rdkit import Chem
    except Exception:
        for site_path in input_skill_site_packages():
            if site_path.exists() and str(site_path) not in sys.path:
                sys.path.insert(0, str(site_path))
        try:
            from rdkit import Chem
        except Exception:
            return [], ["RDKit is not importable; ring candidates could not be inferred from SMILES."]
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return [], [f"RDKit could not parse SMILES: {smiles!r}"]
    candidates: list[dict[str, Any]] = []
    for idx, ring in enumerate(Chem.GetSymmSSSR(mol), start=1):
        atoms0 = list(ring)
        aromatic = all(mol.GetAtomWithIdx(atom).GetIsAromatic() for atom in atoms0)
        symbols = [mol.GetAtomWithIdx(atom).GetSymbol() for atom in atoms0]
        candidates.append(
            {
                "id": idx,
                "atoms": [atom + 1 for atom in atoms0],
                "size": len(atoms0),
                "aromatic": aromatic,
                "elements": symbols,
            }
        )
    if len(candidates) > 1:
        return candidates, ["Multiple rings detected; confirm --ring-atoms before running an aromaticity analysis."]
    if len(candidates) == 1:
        return candidates, ["One ring candidate was detected; confirm --ring-atoms before production use."]
    return candidates, ["No ring was detected from SMILES; provide --ring-atoms if a ring exists."]


def input_skill_site_packages() -> list[Path]:
    venv = REPO_SKILLS / "input-skill" / ".venv"
    patterns = [venv / "Lib" / "site-packages"]
    lib_dir = venv / "lib"
    if lib_dir.exists():
        patterns.extend(sorted(lib_dir.glob("python*/site-packages")))
    return [path for path in patterns if path.exists()]


def which_any(names: Iterable[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())
    return None


def first_existing(patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        for match in glob.glob(os.path.expanduser(pattern)):
            path = Path(match)
            if path.exists() and os.access(path, os.X_OK):
                return str(path.resolve())
    return None


def discover_multiwfn(explicit: str | None = None) -> str | None:
    candidates: list[str | None] = [
        explicit,
        os.environ.get("MULTIWFN_BIN"),
        os.environ.get("MULTIWFN"),
        which_any(("Multiwfn", "multiwfn")),
    ]
    if platform.system().lower() == "darwin":
        candidates.append(
            first_existing(
                (
                    "/Users/*/Applications/multiwfn-mac-build/build/Multiwfn",
                    "/Users/*/Applications/multiwfn-mac-build/build/multiwfn",
                    "/Applications/Multiwfn*/Multiwfn",
                    "/usr/local/bin/Multiwfn",
                    "/opt/homebrew/bin/Multiwfn",
                )
            )
        )
    for candidate in candidates:
        if candidate and Path(candidate).expanduser().exists():
            return str(Path(candidate).expanduser().resolve())
    return None


def multiwfn_env(multiwfn_bin: str) -> dict[str, str]:
    env = os.environ.copy()
    if env.get("Multiwfnpath") and (Path(env["Multiwfnpath"]).expanduser() / "settings.ini").exists():
        return env
    exe = Path(multiwfn_bin)
    for candidate in (exe.parent.parent, exe.parent):
        if (candidate / "settings.ini").exists():
            env["Multiwfnpath"] = str(candidate)
            break
    return env


def input_skill_script() -> Path:
    return REPO_SKILLS / "input-skill" / "scripts" / "input_pipeline.py"


def prepare_with_input_skill(
    args: argparse.Namespace,
    outdir: Path,
    methods: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    if not args.smiles:
        return {}
    script = input_skill_script()
    if not script.exists():
        warnings.append("input-skill was not found; SMILES preparation was skipped.")
        return {}
    task = "nmr" if any(method["id"] in MAGNETIC_METHODS for method in methods) else "opt"
    charge = 0 if args.charge is None else args.charge
    multiplicity = 1 if args.multiplicity is None else args.multiplicity
    if args.charge is None or args.multiplicity is None:
        warnings.append("Charge/multiplicity were not provided to aromatic-skill; input-skill fallback used 0/1.")
    prep_dir = outdir / "input-skill-prep"
    cmd = [
        sys.executable,
        str(script),
        "--smiles",
        args.smiles,
        "--task",
        task,
        "--cores",
        str(args.cores),
        "--memory",
        args.memory,
        "--charge",
        str(charge),
        "--multiplicity",
        str(multiplicity),
        "--program",
        "gaussian",
        "--name",
        f"{slugify(args.name)}-{task}",
        "--no-multiwfn",
        "--outdir",
        str(prep_dir),
    ]
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    prep_manifest = prep_dir / "manifest.json"
    if result.returncode != 0 or not prep_manifest.exists():
        warnings.append("input-skill preparation failed; see input_skill_prep.log.")
        (outdir / "input_skill_prep.log").write_text(result.stdout, encoding="utf-8")
        return {"command": cmd, "returncode": result.returncode, "log": str(outdir / "input_skill_prep.log")}
    manifest = json.loads(prep_manifest.read_text(encoding="utf-8"))
    return {
        "command": cmd,
        "returncode": result.returncode,
        "manifest": str(prep_manifest),
        "structure": manifest.get("structure", {}).get("xyz"),
        "template_gjf": str(prep_dir / "template.gjf") if (prep_dir / "template.gjf").exists() else None,
        "gaussian_input": manifest.get("outputs", {}).get("gaussian"),
        "warnings": manifest.get("warnings", []),
    }


def render_method_overview(methods: list[dict[str, Any]]) -> str:
    lines = [
        "# Multiwfn Aromaticity Method Overview",
        "",
        "These methods are grouped by the information they probe. Use the overview first, then choose the method matching the available files and scientific question.",
        "",
    ]
    for method in methods:
        lines.extend(
            [
                f"## {method['label']}",
                "",
                f"- Category: `{method['category']}`",
                f"- Multiwfn route: `{method['multiwfn_entry']}`",
                f"- What it does: {method['summary']}",
                f"- Best for: {method['best_for']}",
                f"- Required inputs: {', '.join(method.get('requires', []))}",
                f"- Main outputs: {', '.join(method.get('outputs', []))}",
                f"- Caveat: {'; '.join(method.get('caveats', []))}",
                "",
            ]
        )
    return "\n".join(lines)


def needs_ring(method: dict[str, Any]) -> bool:
    return any("ring_atoms" in item or "ring" in item for item in method.get("requires", []))


def needs_pi_orbitals(method: dict[str, Any]) -> bool:
    return any("pi_orbitals" in item for item in method.get("requires", []))


def needs_wavefunction(method: dict[str, Any]) -> bool:
    return any("wavefunction" in item for item in method.get("requires", []))


def needs_gaussian_nmr(method: dict[str, Any]) -> bool:
    return method["id"] in MAGNETIC_METHODS or any("gaussian_nmr" in item for item in method.get("requires", []))


def recipe_line(value: str | None, placeholder: str) -> str:
    return value if value else f"<{placeholder}>"


def recipe_for_method(method: dict[str, Any], context: dict[str, Any]) -> str:
    method_id = method["id"]
    ring = recipe_line(context.get("ring_atoms"), "ring atom indices")
    pi = recipe_line(context.get("pi_orbitals"), "pi orbital indices")
    template = recipe_line(context.get("template_gjf"), "Gaussian NMR template with [geometry]")
    gaussian_output = recipe_line(context.get("gaussian_output"), "Gaussian NMR output")
    lines: list[str] = [f"# {method['label']} ({method_id})"]
    if method_id == "homa":
        lines += ["25", "6", "0", ring, "q", "-1", "0"]
    elif method_id == "bird":
        lines += ["25", "6", "2", ring, "q", "-1", "0"]
    elif method_id == "homac":
        lines += ["25", "6a", ring, "q", "0"]
    elif method_id == "homer":
        lines += ["25", "6b", ring, "q", "0"]
    elif method_id == "mcbo":
        lines += ["25", "1", ring, "0", "0"]
    elif method_id == "mcbo-nao":
        lines += ["25", "-1", ring, "0", "0"]
    elif method_id == "av1245":
        lines += ["25", "2", ring, "q", "0"]
    elif method_id == "icss":
        if context.get("gaussian_output"):
            lines += ["25", "3", "y", gaussian_output, "1", "2", "0"]
        else:
            lines += ["25", "3", "n", template, "# Run generated NICS0001.gjf... with Gaussian, then resume with --gaussian-output."]
    elif method_id == "nics-zz":
        lines += ["25", "4", "", ring, "<paste magnetic shielding tensor or use --tensor/--normal-vector for local projection>"]
    elif method_id == "nics-1d":
        lines += ["25", "13", "2", ring, "", "", "", "2" if context.get("gaussian_output") else "1"]
        if context.get("gaussian_output"):
            lines += [gaussian_output, "3", "", "0"]
        else:
            lines += [template, "0"]
    elif method_id == "nics-2d":
        lines += [
            "25",
            "14",
            "<define NICS-2D plane/grid in Multiwfn prompts>",
            "2" if context.get("gaussian_output") else "1",
            gaussian_output if context.get("gaussian_output") else template,
        ]
    elif method_id == "elf-lol-pi":
        lines += ["# Multiwfn redirects this to plane/grid/topology modules.", "100", "22", pi]
    elif method_id == "shannon":
        lines += ["2", "<complete topology search>", "20", "0"]
    elif method_id == "pdi":
        lines += ["15", "5", ring, "q", "0"]
    elif method_id == "flu":
        lines += ["15", "6", ring, "q", "0"]
    elif method_id == "flu-pi":
        lines += ["15", "7", pi, ring, "q", "0"]
    elif method_id == "plr":
        lines += ["15", "10", ring, "q", "0"]
    elif method_id == "ita":
        lines += ["15", "12", ring, "0"]
    elif method_id == "ring-cp":
        lines += ["2", "<complete topology search and select ring critical point>", "0"]
    elif method_id == "lolipop":
        lines += ["100", "14", "1", pi, "0", ring, "-1"]
    else:
        lines += [f"# No recipe is registered for {method_id}."]
    return "\n".join(lines) + "\n"


def write_recipe(path: Path, methods: list[dict[str, Any]], context: dict[str, Any]) -> str:
    parts = []
    for method in methods:
        parts.append(recipe_for_method(method, context))
    recipe = "\n".join(parts)
    path.write_text(recipe, encoding="utf-8")
    return recipe


def has_placeholders(recipe: str) -> bool:
    return bool(PLACEHOLDER_RE.search(recipe))


def render_plan(
    methods: list[dict[str, Any]],
    context: dict[str, Any],
    warnings: list[str],
    recipe_path: Path,
) -> str:
    lines = [
        "# Aromaticity Analysis Plan",
        "",
        f"- Methods: {', '.join(method['id'] for method in methods)}",
        f"- Input: `{context.get('input') or 'not provided'}`",
        f"- Gaussian NMR output: `{context.get('gaussian_output') or 'not provided'}`",
        f"- Ring atoms: `{context.get('ring_atoms') or 'not confirmed'}`",
        f"- Pi orbitals: `{context.get('pi_orbitals') or 'not confirmed'}`",
        f"- Multiwfn recipe: `{recipe_path}`",
        "",
        "## Next Actions",
        "",
    ]
    if context.get("ring_candidates"):
        lines.append("Confirm one of the ring candidates or pass `--ring-atoms` explicitly before production analysis.")
    if any(needs_gaussian_nmr(method) for method in methods) and not context.get("gaussian_output"):
        lines.append("Run the generated Gaussian NMR/Bq input, then resume with `--gaussian-output <file>`.")
    if any(needs_pi_orbitals(method) for method in methods) and not context.get("pi_orbitals"):
        lines.append("Confirm pi orbital indices with `--pi-orbitals` before FLU-pi/LOLIPOP analysis.")
    if not lines[-1].startswith("Confirm") and not lines[-1].startswith("Run") and not lines[-1].startswith("Confirm pi"):
        lines.append("Inspect the generated recipe, then rerun with `--execute` when inputs are concrete.")
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines) + "\n"


def run_command(
    cmd: list[str],
    cwd: Path,
    stdin_text: str,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            input=stdin_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        output += f"\nCommand timed out after {timeout} seconds.\n"
        return {"command": cmd, "cwd": str(cwd), "returncode": 124, "output": output}
    return {"command": cmd, "cwd": str(cwd), "returncode": proc.returncode, "output": proc.stdout}


def maybe_run_multiwfn(
    args: argparse.Namespace,
    outdir: Path,
    context: dict[str, Any],
    recipe: str,
    warnings: list[str],
) -> dict[str, Any]:
    log_path = outdir / "multiwfn_aromatic.log"
    if not args.execute:
        log_path.write_text("Dry run: Multiwfn was not executed.\n", encoding="utf-8")
        return {"skipped": True, "reason": "dry_run", "log": str(log_path)}
    if has_placeholders(recipe):
        warnings.append("Multiwfn execution skipped because the recipe still contains placeholders.")
        log_path.write_text("Skipped: recipe contains placeholders.\n", encoding="utf-8")
        return {"skipped": True, "reason": "recipe_has_placeholders", "log": str(log_path)}
    input_path = context.get("input")
    if not input_path:
        warnings.append("Multiwfn execution skipped because no input file is available.")
        log_path.write_text("Skipped: no input file.\n", encoding="utf-8")
        return {"skipped": True, "reason": "missing_input", "log": str(log_path)}
    multiwfn_bin = discover_multiwfn(args.multiwfn_bin)
    if not multiwfn_bin:
        warnings.append("Multiwfn executable was not found; recipe was generated but not executed.")
        log_path.write_text("Skipped: Multiwfn executable not found.\n", encoding="utf-8")
        return {"skipped": True, "reason": "missing_multiwfn", "log": str(log_path)}
    result = run_command(
        [multiwfn_bin, input_path],
        outdir,
        recipe + "\n",
        args.timeout,
        env=multiwfn_env(multiwfn_bin),
    )
    log_path.write_text(result["output"], encoding="utf-8")
    clean = {key: value for key, value in result.items() if key != "output"}
    clean["log"] = str(log_path)
    clean["multiwfn"] = multiwfn_bin
    return clean


def write_parsed_nmr_outputs(
    outdir: Path,
    methods: list[dict[str, Any]],
    gaussian_output: Path | None,
    args: argparse.Namespace,
    warnings: list[str],
) -> dict[str, Any]:
    if gaussian_output is None or not gaussian_output.exists():
        return {}
    tensors = parse_gaussian_nmr_tensors(gaussian_output)
    outputs: dict[str, Any] = {"tensor_count": len(tensors)}
    if not tensors:
        warnings.append("Gaussian output was provided, but no shielding tensor blocks were parsed.")
        return outputs
    tensor_path = outdir / "parsed_nmr_tensors.json"
    tensor_path.write_text(json.dumps(tensors, indent=2), encoding="utf-8")
    outputs["parsed_tensors"] = str(tensor_path)

    method_ids = {method["id"] for method in methods}
    if "nics-1d" in method_ids or "icss" in method_ids:
        nics_path = outdir / "NICS_1D.txt"
        lines = ["# index position_A nics_isotropic_ppm line is_bq"]
        for idx, tensor in enumerate(tensors, start=1):
            lines.append(
                f"{idx:6d} {idx - 1:12.6f} {-tensor['isotropic']:14.6f} {tensor['line']:8d} {int(bool(tensor.get('is_bq')))}"
            )
        nics_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        outputs["nics_1d_fallback"] = str(nics_path)
        warnings.append("NICS_1D.txt was written by the fallback parser; use Multiwfn execution for coordinates and component selection.")

    normal = parse_vector(args.normal_vector)
    tensor = parse_tensor(args.tensor)
    if "nics-zz" in method_ids and normal and tensor:
        value = nics_zz_from_tensor(tensor, normal)
        nicszz_path = outdir / "NICS_ZZ.json"
        nicszz_path.write_text(json.dumps({"nics_zz": value, "normal": normal, "tensor": tensor}, indent=2), encoding="utf-8")
        outputs["nics_zz"] = str(nicszz_path)
    elif "nics-zz" in method_ids and not (normal and tensor):
        warnings.append("NICS_ZZ needs --normal-vector and --tensor for local projection, or manual Multiwfn tensor input.")
    return outputs


def aromatic_summary(methods: list[dict[str, Any]], context: dict[str, Any], results: dict[str, Any]) -> str:
    lines = [
        "# Aromaticity Summary",
        "",
        f"- Methods: {', '.join(method['label'] for method in methods)}",
        f"- Ring atoms: `{context.get('ring_atoms') or 'not confirmed'}`",
        f"- Pi orbitals: `{context.get('pi_orbitals') or 'not confirmed'}`",
        f"- Input role: `{context.get('input_role', {}).get('role', 'unknown')}`",
        "",
        "## Results",
        "",
    ]
    parsed = results.get("parsed_outputs", {})
    if parsed:
        for key, value in parsed.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- No numeric aromaticity result has been parsed yet.")
    if results.get("multiwfn", {}).get("skipped"):
        lines.append(f"- Multiwfn: skipped ({results['multiwfn'].get('reason')})")
    elif results.get("multiwfn"):
        lines.append(f"- Multiwfn return code: `{results['multiwfn'].get('returncode')}`")
    return "\n".join(lines) + "\n"


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    if not args.aromatic:
        raise PipelineError("Pass --aromatic to run aromatic-skill.")
    library = load_method_library()
    methods = resolve_methods(args.method, library)
    outdir = make_output_dir(args)
    warnings: list[str] = []

    resume: dict[str, Any] = {}
    if args.resume_manifest:
        resume_path = expand(args.resume_manifest)
        if resume_path and resume_path.exists():
            resume = json.loads(resume_path.read_text(encoding="utf-8"))
        else:
            warnings.append("Requested resume manifest was not found.")

    input_path = expand(args.input)
    gaussian_output = expand(args.gaussian_output)
    if input_path and gaussian_output is None:
        role = detect_file_role(input_path)
        if role.get("role") == "gaussian_nmr_output":
            gaussian_output = input_path
    input_role = detect_file_role(input_path)
    gaussian_role = detect_file_role(gaussian_output)
    if input_role.get("role") == "gaussian_nmr_output" or gaussian_role.get("role") == "gaussian_nmr_output":
        warnings.append("Gaussian NMR output was detected; ask the user whether to continue NICS/ICSS aromaticity post-processing.")
    if input_role.get("role") == "orca_output":
        warnings.append("ORCA output was detected; v1 does not parse ORCA NMR for NICS/ICSS, but converted wavefunction files can be used for non-magnetic aromaticity methods.")
    if input_role.get("role") == "multiwfn_output":
        warnings.append("Multiwfn output was detected; inspect it for aromaticity result text before deciding whether to rerun or summarize.")

    ring_atoms = format_int_list(parse_int_list(args.ring_atoms)) if args.ring_atoms else None
    pi_orbitals = format_int_list(parse_int_list(args.pi_orbitals)) if args.pi_orbitals else None
    ring_candidates, ring_warnings = rdkit_ring_candidates(args.smiles)
    warnings.extend(ring_warnings)
    if any(needs_ring(method) for method in methods) and not ring_atoms:
        warnings.append("Ring atoms are required for at least one selected method; confirm with --ring-atoms.")
    if any(needs_pi_orbitals(method) for method in methods) and not pi_orbitals:
        warnings.append("Pi orbitals are required for at least one selected method; confirm with --pi-orbitals.")

    input_prep = {}
    if args.smiles and not input_path:
        input_prep = prepare_with_input_skill(args, outdir, methods, warnings)
        if input_prep.get("structure"):
            input_path = Path(input_prep["structure"])
            input_role = detect_file_role(input_path)

    template_gjf = input_prep.get("template_gjf")
    if resume and not template_gjf:
        template_gjf = resume.get("context", {}).get("template_gjf")

    context = {
        "input": str(input_path) if input_path else None,
        "input_role": input_role,
        "gaussian_output": str(gaussian_output) if gaussian_output else None,
        "gaussian_output_role": gaussian_role,
        "template_gjf": template_gjf,
        "ring_atoms": ring_atoms,
        "pi_orbitals": pi_orbitals,
        "ring_candidates": ring_candidates,
        "input_skill_prep": input_prep,
    }

    overview = render_method_overview(library["methods"])
    overview_path = outdir / "method_overview.md"
    overview_path.write_text(overview, encoding="utf-8")

    recipe_path = outdir / "multiwfn_aromatic.inp"
    recipe = write_recipe(recipe_path, methods, context)

    plan = render_plan(methods, context, warnings, recipe_path)
    plan_path = outdir / "aromatic_plan.md"
    plan_path.write_text(plan, encoding="utf-8")

    parsed_outputs = write_parsed_nmr_outputs(outdir, methods, gaussian_output, args, warnings)
    multiwfn_result = maybe_run_multiwfn(args, outdir, context, recipe, warnings)

    results = {
        "methods": [method["id"] for method in methods],
        "parsed_outputs": parsed_outputs,
        "multiwfn": multiwfn_result,
        "warnings": warnings,
    }
    results_path = outdir / "aromatic_results.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    summary_path = outdir / "aromatic_summary.md"
    summary_path.write_text(aromatic_summary(methods, context, results), encoding="utf-8")

    manifest_path = outdir / "manifest.json"
    manifest = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "method": args.method,
            "smiles": args.smiles,
            "input": str(input_path) if input_path else None,
            "gaussian_output": str(gaussian_output) if gaussian_output else None,
            "ring_atoms": ring_atoms,
            "pi_orbitals": pi_orbitals,
            "execute": args.execute,
            "resume_manifest": args.resume_manifest,
        },
        "methods": methods,
        "context": context,
        "outputs": {
            "method_overview": str(overview_path),
            "aromatic_plan": str(plan_path),
            "aromatic_results": str(results_path),
            "aromatic_summary": str(summary_path),
            "manifest": str(manifest_path),
            "multiwfn_recipe": str(recipe_path),
            "multiwfn_log": str(outdir / "multiwfn_aromatic.log"),
            **parsed_outputs,
        },
        "warnings": warnings,
        "resume": resume,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.explain:
        print(overview)
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = run_pipeline(args)
    except PipelineError as exc:
        print(f"aromatic-skill error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"outputs": manifest["outputs"], "warnings": manifest["warnings"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
