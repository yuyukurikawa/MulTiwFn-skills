#!/usr/bin/env python3
"""Generate Gaussian and ORCA input files from a SMILES string."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import venv
from typing import Any, Iterable


TASKS = (
    "sp",
    "opt",
    "freq",
    "opt-freq",
    "tddft",
    "nmr",
    "interaction-sp",
    "high-accuracy-sp",
)
PROGRAMS = ("orca", "gaussian", "both")
SKILL_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_LIBRARY = SKILL_ROOT / "references" / "benchmark-library.yml"
SKILL_VENV = SKILL_ROOT / ".venv"
DEFAULT_SEED = 61453
TRANSITION_METALS = {
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
}


class PipelineError(RuntimeError):
    """Recoverable pipeline failure with a user-facing message."""


class MissingDependency(PipelineError):
    """Raised when RDKit is unavailable."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Gaussian and ORCA input files from a SMILES string."
    )
    parser.add_argument("--setup", action="store_true", help="Create skill-local .venv and install RDKit.")
    parser.add_argument("--smiles", help="Input SMILES string.")
    parser.add_argument("--program", choices=PROGRAMS, default="both")
    parser.add_argument("--task", choices=TASKS, help="Calculation task type.")
    parser.add_argument("--cores", type=int, help="Number of CPU cores.")
    parser.add_argument("--memory", help="Total job memory, e.g. 8GB or 64000MB.")
    parser.add_argument("--charge", type=int, help="Net charge.")
    parser.add_argument("--multiplicity", type=int, help="Spin multiplicity.")
    parser.add_argument("--name", default="molecule", help="Output basename.")
    parser.add_argument("--workdir", default=".", help="Directory where input-skill-run is created.")
    parser.add_argument("--outdir", help="Explicit output directory.")
    parser.add_argument("--multiwfn-bin", help="Path to Multiwfn executable.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RDKit ETKDG random seed.")
    parser.add_argument("--timeout", type=int, default=180, help="External command timeout in seconds.")
    parser.add_argument(
        "--no-multiwfn",
        action="store_true",
        help="Render final inputs by local template injection instead of running Multiwfn.",
    )
    return parser.parse_args(argv)


def require_generation_args(args: argparse.Namespace) -> None:
    missing = [
        name
        for name in ("smiles", "task", "cores", "memory", "charge", "multiplicity")
        if getattr(args, name) is None
    ]
    if missing:
        raise PipelineError("Missing required arguments: " + ", ".join(f"--{name}" for name in missing))
    if args.cores < 1:
        raise PipelineError("--cores must be >= 1")
    if args.multiplicity < 1:
        raise PipelineError("--multiplicity must be >= 1")


def venv_python() -> Path:
    if platform.system().lower() == "windows":
        return SKILL_VENV / "Scripts" / "python.exe"
    return SKILL_VENV / "bin" / "python"


def rdkit_importable() -> bool:
    try:
        import rdkit  # noqa: F401
    except Exception:
        return False
    return True


def maybe_reexec_with_skill_venv() -> None:
    py = venv_python()
    if rdkit_importable() or not py.exists():
        return
    if Path(sys.prefix).resolve() == SKILL_VENV.resolve():
        return
    if os.environ.get("INPUT_SKILL_NO_REEXEC"):
        return
    env = os.environ.copy()
    env["INPUT_SKILL_VENV_ACTIVE"] = "1"
    os.execvpe(str(py), [str(py), str(Path(__file__).resolve()), *sys.argv[1:]], env)


def setup_rdkit() -> None:
    SKILL_VENV.parent.mkdir(parents=True, exist_ok=True)
    if not venv_python().exists():
        builder = venv.EnvBuilder(with_pip=True, clear=False)
        builder.create(SKILL_VENV)
    py = venv_python()
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(py), "-m", "pip", "install", "rdkit"], check=True)
    subprocess.run([str(py), "-c", "import rdkit; print(rdkit.__version__)"], check=True)


def parse_memory_to_mb(value: str) -> int:
    text = value.strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?i?b?|[kmgt])?", text, re.I)
    if not match:
        raise PipelineError(f"Cannot parse memory value: {value!r}")
    amount = float(match.group(1))
    unit = (match.group(2) or "MB").lower()
    unit = unit.replace("ib", "b")
    factors = {
        "": 1,
        "m": 1,
        "mb": 1,
        "g": 1024,
        "gb": 1024,
        "t": 1024 * 1024,
        "tb": 1024 * 1024,
        "k": 1 / 1024,
        "kb": 1 / 1024,
        "b": 1 / (1024 * 1024),
    }
    if unit not in factors:
        raise PipelineError(f"Unsupported memory unit in {value!r}")
    mb = int(math.floor(amount * factors[unit]))
    if mb < 1:
        raise PipelineError("--memory must be at least 1 MB")
    return mb


def format_memory_for_gaussian(memory_mb: int) -> str:
    if memory_mb % 1024 == 0:
        return f"{memory_mb // 1024}GB"
    return f"{memory_mb}MB"


def orca_maxcore_mb(total_memory_mb: int, cores: int) -> int:
    return max(1, int(math.floor(total_memory_mb * 0.75 / cores)))


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug[:80] or "molecule"


def timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def load_benchmark_library(path: Path = BENCHMARK_LIBRARY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_rule(task: str, library: dict[str, Any]) -> dict[str, Any]:
    for rule in library.get("rules", []):
        if rule.get("task") == task:
            return rule
    raise PipelineError(f"No benchmark rule found for task {task!r}")


def discover_multiwfn(explicit: str | None = None) -> str | None:
    candidates: list[str | None] = [
        explicit,
        os.environ.get("MULTIWFN_BIN"),
        os.environ.get("MULTIWFN"),
        shutil.which("Multiwfn"),
        shutil.which("multiwfn"),
    ]
    if platform.system().lower() == "darwin":
        candidates.extend(
            [
                first_existing(
                    [
                        "/Users/*/Applications/multiwfn-mac-build/build/Multiwfn",
                        "/Users/*/Applications/multiwfn-mac-build/build/multiwfn",
                        "/Applications/Multiwfn*/Multiwfn",
                        "/opt/homebrew/bin/Multiwfn",
                        "/usr/local/bin/Multiwfn",
                    ]
                )
            ]
        )
    for candidate in candidates:
        if candidate and Path(candidate).expanduser().exists():
            return str(Path(candidate).expanduser().resolve())
    return None


def first_existing(patterns: Iterable[str]) -> str | None:
    import glob

    for pattern in patterns:
        for match in glob.glob(os.path.expanduser(pattern)):
            path = Path(match)
            if path.exists() and os.access(path, os.X_OK):
                return str(path.resolve())
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


def generate_rdkit_structure(smiles: str, charge: int, multiplicity: int, seed: int) -> dict[str, Any]:
    try:
        import rdkit
        from rdkit import Chem
        from rdkit.Chem import AllChem, rdMolDescriptors
    except Exception as exc:
        raise MissingDependency(
            "RDKit is not available. Ask the user before running "
            "`python3 skills/input-skill/scripts/input_pipeline.py --setup`."
        ) from exc

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise PipelineError(f"RDKit could not parse SMILES: {smiles!r}")

    warnings: list[str] = []
    formal_charge = Chem.GetFormalCharge(mol)
    if formal_charge != charge:
        warnings.append(
            f"RDKit formal charge is {formal_charge}, but user-specified charge is {charge}; verify before submitting."
        )

    unassigned = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    if any(center[1] == "?" for center in unassigned):
        warnings.append("SMILES contains unassigned stereocenters; generated 3D geometry is only one possible stereochemical model.")

    mol_h = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = int(seed)
    embed_status = AllChem.EmbedMolecule(mol_h, params)
    if embed_status != 0:
        params.useRandomCoords = True
        embed_status = AllChem.EmbedMolecule(mol_h, params)
    if embed_status != 0:
        raise PipelineError("RDKit failed to embed a 3D conformer from the SMILES string.")

    optimizer = "MMFF"
    props = AllChem.MMFFGetMoleculeProperties(mol_h, mmffVariant="MMFF94s")
    if props is not None:
        opt_status = AllChem.MMFFOptimizeMolecule(mol_h, mmffVariant="MMFF94s", maxIters=500)
    else:
        optimizer = "UFF"
        opt_status = AllChem.UFFOptimizeMolecule(mol_h, maxIters=500)
    if opt_status == 1:
        warnings.append(f"RDKit {optimizer} optimization did not fully converge within 500 iterations.")

    conf = mol_h.GetConformer()
    atoms: list[dict[str, Any]] = []
    transition_metals: set[str] = set()
    for atom in mol_h.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        symbol = atom.GetSymbol()
        if symbol in TRANSITION_METALS:
            transition_metals.add(symbol)
        atoms.append({"symbol": symbol, "x": pos.x, "y": pos.y, "z": pos.z})

    if transition_metals:
        warnings.append(
            "Transition-metal atoms detected ("
            + ", ".join(sorted(transition_metals))
            + "); v1 benchmark rules are not broadly validated for all metal spin/oxidation states."
        )
    if multiplicity > 1:
        warnings.append("Open-shell multiplicity requested; inspect method suitability and SCF stability.")

    return {
        "rdkit_version": rdkit.__version__,
        "smiles": Chem.MolToSmiles(mol, isomericSmiles=True),
        "formula": rdMolDescriptors.CalcMolFormula(mol_h),
        "formal_charge": formal_charge,
        "optimizer": optimizer,
        "seed": seed,
        "atoms": atoms,
        "transition_metals": sorted(transition_metals),
        "warnings": warnings,
    }


def write_xyz(path: Path, structure: dict[str, Any], charge: int, multiplicity: int) -> None:
    atoms = structure["atoms"]
    lines = [
        str(len(atoms)),
        f"SMILES={structure['smiles']} charge={charge} multiplicity={multiplicity} seed={structure['seed']} generated_by=input-skill",
    ]
    for atom in atoms:
        lines.append(f"{atom['symbol']:<2} {atom['x']:14.8f} {atom['y']:14.8f} {atom['z']:14.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def geometry_lines(atoms: list[dict[str, Any]]) -> list[str]:
    return [f"{atom['symbol']:<2} {atom['x']:14.8f} {atom['y']:14.8f} {atom['z']:14.8f}" for atom in atoms]


def render_gaussian_template(
    rule: dict[str, Any],
    cores: int,
    memory_mb: int,
    charge: int,
    multiplicity: int,
    name: str,
) -> str:
    route = rule["gaussian"]["route"]
    memory = format_memory_for_gaussian(memory_mb)
    return "\n".join(
        [
            f"%nprocshared={cores}",
            f"%mem={memory}",
            f"%chk={name}.chk",
            route,
            "",
            f"{rule['label']} generated by input-skill",
            "",
            f"{charge} {multiplicity}",
            "[geometry]",
            "",
            "",
        ]
    )


def render_orca_template(
    rule: dict[str, Any],
    cores: int,
    memory_mb: int,
    charge: int,
    multiplicity: int,
) -> str:
    maxcore = orca_maxcore_mb(memory_mb, cores)
    lines = [
        rule["orca"]["keywords"],
        f"%maxcore {maxcore}",
        f"%pal nprocs {cores} end",
    ]
    blocks = rule["orca"].get("blocks", [])
    if blocks:
        lines.extend(["", *blocks])
    lines.extend(["", f"* xyz {charge} {multiplicity_str(multiplicity)}", "[geometry]", "*", ""])
    return "\n".join(lines)


def multiplicity_str(multiplicity: int) -> str:
    return str(multiplicity)


def inject_geometry(template: str, atoms: list[dict[str, Any]]) -> str:
    replacement = "\n".join(geometry_lines(atoms))
    return template.replace("[geometry]", replacement)


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
        return {
            "command": cmd,
            "cwd": str(cwd),
            "stdin": stdin_text,
            "returncode": 124,
            "output": output,
        }
    return {
        "command": cmd,
        "cwd": str(cwd),
        "stdin": stdin_text,
        "returncode": proc.returncode,
        "output": proc.stdout,
    }


def run_multiwfn_gaussian(multiwfn_bin: str, outdir: Path, final_name: str, timeout: int) -> dict[str, Any]:
    result = run_command(
        [multiwfn_bin, "structure.xyz"],
        outdir,
        f"gi\n{final_name}\nq\n",
        timeout,
        env=multiwfn_env(multiwfn_bin),
    )
    (outdir / "multiwfn_gaussian.log").write_text(result["output"], encoding="utf-8")
    return result


def run_multiwfn_orca(multiwfn_bin: str, outdir: Path, final_name: str, timeout: int) -> dict[str, Any]:
    result = run_command(
        [multiwfn_bin, "structure.xyz"],
        outdir,
        f"oi\n{final_name}\n-100\ntemplate.orca.inp\nq\n",
        timeout,
        env=multiwfn_env(multiwfn_bin),
    )
    (outdir / "multiwfn_orca.log").write_text(result["output"], encoding="utf-8")
    return result


def write_recommendation(
    path: Path,
    args: argparse.Namespace,
    rule: dict[str, Any],
    memory_mb: int,
    maxcore: int,
    warnings: list[str],
    outputs: dict[str, str],
) -> None:
    lines = [
        "# Input Recommendation",
        "",
        f"- SMILES: `{args.smiles}`",
        f"- Task: `{args.task}`",
        f"- Charge/multiplicity: `{args.charge} {args.multiplicity}`",
        f"- Resources: `{args.cores}` cores, `{format_memory_for_gaussian(memory_mb)}` total memory",
        f"- ORCA maxcore: `{maxcore}` MB/core",
        "",
        "## Selected Rule",
        "",
        f"- Rule: `{rule['id']}`",
        f"- Label: {rule['label']}",
        f"- Chemical space: {rule['chemical_space']}",
        f"- Rationale: {rule['rationale']}",
        "",
        "## Program Keywords",
        "",
        f"- ORCA: `{rule['orca']['keywords']}`",
        f"- Gaussian: `{rule['gaussian']['route']}`",
        "",
        "## Outputs",
        "",
    ]
    for label, output in outputs.items():
        lines.append(f"- {label}: `{output}`")
    lines.extend(["", "## Caveats", ""])
    for caveat in rule.get("caveats", []):
        lines.append(f"- {caveat}")
    for warning in warnings:
        lines.append(f"- Warning: {warning}")
    lines.extend(["", "## References", ""])
    for item in rule.get("evidence", []):
        doi = item.get("doi", "")
        url = item.get("url", "")
        title = item.get("title", "Reference")
        if doi:
            lines.append(f"- {title}. DOI: `{doi}`. {url}")
        else:
            lines.append(f"- {title}. {url}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_output_dir(args: argparse.Namespace) -> Path:
    if args.outdir:
        outdir = Path(args.outdir).expanduser().resolve()
    else:
        outdir = (
            Path(args.workdir).expanduser().resolve()
            / "input-skill-run"
            / f"{slugify(args.name)}-{timestamp()}"
        )
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def program_requested(program: str, candidate: str) -> bool:
    return program == "both" or program == candidate


def run_generation(args: argparse.Namespace) -> dict[str, Any]:
    require_generation_args(args)
    maybe_reexec_with_skill_venv()
    memory_mb = parse_memory_to_mb(args.memory)
    maxcore = orca_maxcore_mb(memory_mb, args.cores)
    library = load_benchmark_library()
    rule = select_rule(args.task, library)
    structure = generate_rdkit_structure(args.smiles, args.charge, args.multiplicity, args.seed)
    warnings = list(structure["warnings"])
    if maxcore < 256:
        warnings.append(
            f"ORCA maxcore is only {maxcore} MB/core after reserving 25%; increase memory or reduce cores."
        )
    if args.task == "high-accuracy-sp" and structure.get("transition_metals"):
        warnings.append("High-accuracy DLPNO-CCSD(T) rule needs extra validation for transition-metal systems.")

    outdir = make_output_dir(args)
    name = slugify(args.name)
    source_smiles = outdir / "source.smiles"
    source_smiles.write_text(args.smiles.strip() + "\n", encoding="utf-8")
    xyz_path = outdir / "structure.xyz"
    write_xyz(xyz_path, structure, args.charge, args.multiplicity)

    gaussian_template = render_gaussian_template(rule, args.cores, memory_mb, args.charge, args.multiplicity, name)
    orca_template = render_orca_template(rule, args.cores, memory_mb, args.charge, args.multiplicity)
    (outdir / "template.gjf").write_text(gaussian_template, encoding="utf-8")
    (outdir / "template.orca.inp").write_text(orca_template, encoding="utf-8")

    outputs: dict[str, str] = {}
    commands: list[dict[str, Any]] = []
    multiwfn_bin = None if args.no_multiwfn else discover_multiwfn(args.multiwfn_bin)
    atoms = structure["atoms"]

    if program_requested(args.program, "gaussian"):
        final = outdir / f"{name}.gjf"
        if multiwfn_bin:
            result = run_multiwfn_gaussian(multiwfn_bin, outdir, final.name, args.timeout)
            commands.append({k: v for k, v in result.items() if k != "output"})
            if result["returncode"] != 0 or not final.exists():
                warnings.append("Multiwfn Gaussian generation failed; used local template injection fallback.")
                final.write_text(inject_geometry(gaussian_template, atoms), encoding="utf-8")
        else:
            warnings.append("Multiwfn not found or disabled; Gaussian file used local template injection fallback.")
            final.write_text(inject_geometry(gaussian_template, atoms), encoding="utf-8")
        outputs["gaussian"] = str(final)

    if program_requested(args.program, "orca"):
        final = outdir / f"{name}.inp"
        if multiwfn_bin:
            result = run_multiwfn_orca(multiwfn_bin, outdir, final.name, args.timeout)
            commands.append({k: v for k, v in result.items() if k != "output"})
            if result["returncode"] != 0 or not final.exists():
                warnings.append("Multiwfn ORCA generation failed; used local template injection fallback.")
                final.write_text(inject_geometry(orca_template, atoms), encoding="utf-8")
        else:
            warnings.append("Multiwfn not found or disabled; ORCA file used local template injection fallback.")
            final.write_text(inject_geometry(orca_template, atoms), encoding="utf-8")
        outputs["orca"] = str(final)

    recommendation_path = outdir / "recommendation.md"
    write_recommendation(recommendation_path, args, rule, memory_mb, maxcore, warnings, outputs)
    outputs["recommendation"] = str(recommendation_path)

    manifest_path = outdir / "manifest.json"
    outputs["manifest"] = str(manifest_path)

    manifest = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "smiles": args.smiles,
            "program": args.program,
            "task": args.task,
            "cores": args.cores,
            "memory": args.memory,
            "memory_mb": memory_mb,
            "charge": args.charge,
            "multiplicity": args.multiplicity,
            "name": name,
        },
        "structure": {
            "source_smiles": structure["smiles"],
            "formula": structure["formula"],
            "formal_charge": structure["formal_charge"],
            "atom_count": len(structure["atoms"]),
            "transition_metals": structure["transition_metals"],
            "xyz": str(xyz_path),
        },
        "rdkit": {
            "version": structure["rdkit_version"],
            "seed": structure["seed"],
            "optimizer": structure["optimizer"],
        },
        "resources": {
            "gaussian_memory": format_memory_for_gaussian(memory_mb),
            "orca_maxcore_mb": maxcore,
        },
        "selected_rule": rule,
        "tools": {
            "multiwfn": multiwfn_bin,
            "multiwfn_disabled": bool(args.no_multiwfn),
        },
        "commands": commands,
        "outputs": outputs,
        "warnings": warnings,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.setup:
            setup_rdkit()
            return 0
        manifest = run_generation(args)
    except PipelineError as exc:
        print(f"input-skill error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"outputs": manifest["outputs"], "warnings": manifest["warnings"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
