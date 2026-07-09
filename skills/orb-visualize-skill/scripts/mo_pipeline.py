#!/usr/bin/env python3
"""Discover inputs/tools, generate MO cubes, and render front/side orbital views."""

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
import struct
import subprocess
import sys
from typing import Iterable


WAVEFUNCTION_EXTS = {
    ".fchk": 100,
    ".fch": 98,
    ".wfx": 92,
    ".wfn": 90,
    ".molden": 82,
    ".mwfn": 80,
}
CUBE_EXTS = {".cube", ".cub"}
STRUCTURE_EXTS = {".xyz", ".mol", ".sdf", ".pdb", ".mol2"}
ORBITAL_KEYS = ("orb", "orbital", "mo", "homo", "lumo")
DEFAULT_NEGATIVE_COLOR = "#5BCEFA"
DEFAULT_POSITIVE_COLOR = "#F5A9B8"
COLOR_ALIASES = {
    "black": "#000000",
    "blue": "#0000FF",
    "cyan": "#00FFFF",
    "green": "#008000",
    "grey": "#808080",
    "gray": "#808080",
    "orange": "#FFA500",
    "pink": "#FFC0CB",
    "purple": "#800080",
    "red": "#FF0000",
    "trans-blue": DEFAULT_NEGATIVE_COLOR,
    "trans-pink": DEFAULT_POSITIVE_COLOR,
    "transgender-blue": DEFAULT_NEGATIVE_COLOR,
    "transgender-pink": DEFAULT_POSITIVE_COLOR,
    "white": "#FFFFFF",
    "yellow": "#FFFF00",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Molecular orbital front/side rendering pipeline for Multiwfn, VMD, and ChimeraX."
    )
    parser.add_argument("--MO", required=True, help="Comma-separated orbitals, e.g. HOMO,LUMO,HOMO-1,45.")
    parser.add_argument("--homo", type=int, help="HOMO orbital index required for HOMO/LUMO labels.")
    parser.add_argument("--workdir", default=".", help="Primary directory to search.")
    parser.add_argument("--search-root", action="append", default=[], help="Extra search root.")
    parser.add_argument("--search-home", action="store_true", help="Search the user home directory.")
    parser.add_argument("--max-depth", type=int, default=4, help="Maximum recursive search depth.")
    parser.add_argument("--input", help="Wavefunction input file.")
    parser.add_argument("--structure", help="Structure file for rendering.")
    parser.add_argument(
        "--cube",
        action="append",
        default=[],
        help="Precomputed orbital cube. May repeat. Accepts path or label=path.",
    )
    parser.add_argument("--outdir", help="Output directory.")
    parser.add_argument("--renderer", choices=("auto", "vmd", "chimerax"), default="auto")
    parser.add_argument("--multiwfn-bin", help="Path to Multiwfn executable.")
    parser.add_argument("--vmd-bin", help="Path to VMD executable.")
    parser.add_argument("--chimerax-bin", help="Path to ChimeraX executable.")
    parser.add_argument("--recipe", help="Custom Multiwfn stdin recipe.")
    parser.add_argument("--isovalue", default="0.03", help="Orbital isosurface value in a.u.")
    parser.add_argument(
        "--negative-color",
        default=DEFAULT_NEGATIVE_COLOR,
        help="Color for negative-valued MO regions. Accepts #RRGGBB, R,G,B, or a common color name.",
    )
    parser.add_argument(
        "--positive-color",
        default=DEFAULT_POSITIVE_COLOR,
        help="Color for positive-valued MO regions. Accepts #RRGGBB, R,G,B, or a common color name.",
    )
    parser.add_argument("--front-axis", help="Manual front view axis: x, -y, z, or vector a,b,c.")
    parser.add_argument("--side-axis", help="Manual side view axis: x, -y, z, or vector a,b,c.")
    parser.add_argument("--width", type=int, default=2400)
    parser.add_argument("--height", type=int, default=1800)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--execute", action="store_true", help="Actually run external programs.")
    return parser.parse_args()


def expand(path: str | Path | None) -> Path | None:
    if not path:
        return None
    return Path(path).expanduser().resolve()


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
            if path.exists() and (path.is_dir() or os.access(path, os.X_OK)):
                return str(path.resolve())
    return None


def discover_tools(args: argparse.Namespace) -> dict:
    system = platform.system().lower()
    tools = {
        "multiwfn": args.multiwfn_bin
        or os.environ.get("MULTIWFN_BIN")
        or os.environ.get("MULTIWFN")
        or which_any(("Multiwfn", "multiwfn")),
        "vmd": args.vmd_bin
        or os.environ.get("VMD_BIN")
        or which_any(("vmd", "VMD")),
        "chimerax": args.chimerax_bin
        or os.environ.get("CHIMERAX_BIN")
        or os.environ.get("CHIMERAX")
        or which_any(("ChimeraX", "chimerax", "ucsf-chimerax")),
        "tachyon": os.environ.get("TACHYON_BIN")
        or which_any(("tachyon", "tachyon_MACOSXARM64", "tachyon_LINUXAMD64")),
    }
    multiwfnpath = os.environ.get("Multiwfnpath")
    vmd_home = None

    if system == "darwin":
        tools["multiwfn"] = tools["multiwfn"] or first_existing(
            (
                "/Users/*/Applications/multiwfn-mac-build/build/Multiwfn",
                "/Users/*/Applications/multiwfn-mac-build/build/multiwfn",
                "/Applications/Multiwfn*/Multiwfn",
                "/usr/local/bin/Multiwfn",
                "/opt/homebrew/bin/Multiwfn",
            )
        )
        tools["vmd"] = tools["vmd"] or first_existing(
            (
                "/Applications/VMD*.app/Contents/vmd*/vmd_*",
                "/Applications/VMD*.app/Contents/Resources/VMD.app/Contents/MacOS/VMD",
                "/Applications/VMD*.app/Contents/MacOS/VMD",
                "/Applications/VMD*.app/Contents/MacOS/VMDLauncher",
            )
        )
        tools["chimerax"] = tools["chimerax"] or first_existing(
            (
                "/Applications/ChimeraX*.app/Contents/MacOS/ChimeraX",
                "/Applications/ChimeraX*.app/Contents/bin/ChimeraX",
                "/Applications/UCSF ChimeraX*.app/Contents/MacOS/ChimeraX",
            )
        )
    elif system == "windows":
        tools["multiwfn"] = tools["multiwfn"] or first_existing(
            ("C:/Multiwfn*/Multiwfn.exe", "C:/Program Files/Multiwfn*/Multiwfn.exe")
        )
        tools["vmd"] = tools["vmd"] or first_existing(("C:/Program Files/VMD*/vmd.exe",))
        tools["chimerax"] = tools["chimerax"] or first_existing(
            ("C:/Program Files/ChimeraX*/bin/ChimeraX.exe",)
        )

    if multiwfnpath and not (Path(multiwfnpath).expanduser() / "settings.ini").exists():
        multiwfnpath = None
    if tools.get("multiwfn") and not multiwfnpath:
        exe = Path(tools["multiwfn"])
        candidates = [exe.parent.parent, exe.parent]
        for candidate in candidates:
            if (candidate / "settings.ini").exists():
                multiwfnpath = str(candidate)
                break
    if tools.get("vmd"):
        vmd_path = Path(tools["vmd"])
        if vmd_path.name.startswith("vmd_"):
            vmd_home = str(vmd_path.parent)
        elif "Contents" in vmd_path.parts:
            parts = vmd_path.parts
            idx = parts.index("Contents")
            root = Path(*parts[: idx + 1])
            matches = sorted(root.glob("vmd*/vmd_*"))
            if matches:
                vmd_home = str(matches[0].parent)
    if vmd_home and not tools.get("tachyon"):
        tachyon_matches = sorted(Path(vmd_home).glob("tachyon_*"))
        if tachyon_matches:
            tools["tachyon"] = str(tachyon_matches[0].resolve())

    return {
        "multiwfn": str(Path(tools["multiwfn"]).resolve()) if tools.get("multiwfn") else None,
        "multiwfnpath": multiwfnpath,
        "vmd": str(Path(tools["vmd"]).resolve()) if tools.get("vmd") else None,
        "vmd_home": vmd_home,
        "tachyon": str(Path(tools["tachyon"]).resolve()) if tools.get("tachyon") else None,
        "chimerax": str(Path(tools["chimerax"]).resolve()) if tools.get("chimerax") else None,
    }


def iter_files(root: Path, max_depth: int) -> Iterable[Path]:
    if not root.exists():
        return
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_depth = len(current.relative_to(root).parts)
        if rel_depth >= max_depth:
            dirnames[:] = []
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "Library"}
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".Trash")]
        for filename in filenames:
            yield current / filename


def score_file(path: Path) -> int:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in WAVEFUNCTION_EXTS:
        return WAVEFUNCTION_EXTS[suffix]
    if suffix in CUBE_EXTS:
        base = 65
        if any(key in name for key in ORBITAL_KEYS):
            base += 25
        return base
    if suffix in STRUCTURE_EXTS:
        return 40
    return 0


def split_cube_arg(value: str) -> tuple[str | None, Path]:
    if "=" in value:
        label, path = value.split("=", 1)
        return label.strip(), expand(path)  # type: ignore[return-value]
    return None, expand(value)  # type: ignore[return-value]


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9+-]", "", value.lower())


def sanitize_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", label).strip("_")


def parse_orbitals(spec: str, homo: int | None) -> list[dict]:
    orbitals: list[dict] = []
    for raw in [part.strip() for part in spec.split(",") if part.strip()]:
        if re.fullmatch(r"\d+", raw):
            number = int(raw)
            if number <= 0:
                raise ValueError(f"Invalid orbital number: {raw}")
            orbitals.append({"expr": raw, "label": f"MO{number}", "number": number, "safe": f"MO{number}"})
            continue

        match = re.fullmatch(r"(?i)(HOMO|LUMO)([+-]\d+)?", raw)
        if not match:
            raise ValueError(f"Invalid orbital expression: {raw}")
        if homo is None:
            raise ValueError("HOMO/LUMO labels require --homo <index>.")
        base_name = match.group(1).upper()
        offset = int(match.group(2) or "0")
        base = homo if base_name == "HOMO" else homo + 1
        number = base + offset
        if number <= 0:
            raise ValueError(f"Orbital expression {raw} resolved to invalid index {number}.")
        label = raw.upper()
        orbitals.append({"expr": raw, "label": label, "number": number, "safe": sanitize_label(label)})
    if not orbitals:
        raise ValueError("--MO did not contain any orbital expressions.")
    return orbitals


def orbital_match_tokens(orbital: dict) -> list[str]:
    label = orbital["label"]
    number = int(orbital["number"])
    tokens = [
        label,
        label.replace("+", "plus").replace("-", "minus"),
        f"mo{number}",
        f"mo_{number}",
        f"orb{number}",
        f"orb_{number}",
        f"orbital{number}",
        f"orb{number:03d}",
        f"orb{number:04d}",
        f"orb{number:05d}",
        f"orb{number:06d}",
    ]
    return [normalize_token(token) for token in tokens]


def match_cube_to_orbital(path: Path, orbitals: list[dict], explicit_label: str | None = None) -> dict | None:
    haystack = normalize_token(explicit_label or path.stem)
    for orbital in orbitals:
        if haystack in {normalize_token(orbital["label"]), normalize_token(orbital["expr"]), str(orbital["number"])}:
            return orbital
        for token in orbital_match_tokens(orbital):
            if token and token in haystack:
                return orbital
    return None


def discover_files(args: argparse.Namespace, orbitals: list[dict]) -> dict:
    roots = [expand(args.workdir)]
    roots.extend(expand(root) for root in args.search_root)
    if args.search_home:
        roots.append(Path.home().resolve())
    roots = [root for root in roots if root]

    explicit_wavefunction = expand(args.input)
    explicit_structure = expand(args.structure)
    explicit_cubes = [split_cube_arg(value) for value in args.cube]

    candidates: list[Path] = []
    for root in roots:
        candidates.extend(iter_files(root, args.max_depth))

    wavefunctions = [p for p in candidates if p.suffix.lower() in WAVEFUNCTION_EXTS]
    structures = [p for p in candidates if p.suffix.lower() in STRUCTURE_EXTS]
    cubes = [p for p in candidates if p.suffix.lower() in CUBE_EXTS]
    for _, cube_path in explicit_cubes:
        if cube_path and cube_path.exists() and cube_path not in cubes:
            cubes.append(cube_path)

    def best(paths: list[Path]) -> Path | None:
        if not paths:
            return None
        return sorted(paths, key=lambda p: (score_file(p), p.stat().st_mtime), reverse=True)[0]

    orbital_cubes: dict[str, Path] = {}
    unmatched_explicit_cubes: list[str] = []
    for explicit_label, cube_path in explicit_cubes:
        if not cube_path:
            continue
        matched = match_cube_to_orbital(cube_path, orbitals, explicit_label)
        if matched:
            orbital_cubes[matched["label"]] = cube_path
        else:
            unmatched_explicit_cubes.append(str(cube_path))

    for cube in sorted(cubes, key=lambda p: (score_file(p), p.stat().st_mtime), reverse=True):
        matched = match_cube_to_orbital(cube, orbitals)
        if matched and matched["label"] not in orbital_cubes:
            orbital_cubes[matched["label"]] = cube

    return {
        "wavefunction": explicit_wavefunction or best(wavefunctions),
        "structure": explicit_structure or best(structures),
        "orbital_cubes": orbital_cubes,
        "unmatched_explicit_cubes": unmatched_explicit_cubes,
        "cube_candidates": sorted([str(p) for p in cubes], key=str)[:80],
        "wavefunction_candidates": sorted([str(p) for p in wavefunctions], key=str)[:50],
        "structure_candidates": sorted([str(p) for p in structures], key=str)[:50],
    }


def make_outdir(args: argparse.Namespace) -> Path:
    if args.outdir:
        outdir = expand(args.outdir)
    else:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outdir = expand(args.workdir) / f"mo-output-{stamp}"
    assert outdir is not None
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def parse_color(value: str) -> tuple[float, float, float]:
    raw = value.strip()
    named = COLOR_ALIASES.get(raw.lower())
    if named:
        raw = named
    if re.fullmatch(r"#?[0-9A-Fa-f]{6}", raw):
        hex_value = raw[1:] if raw.startswith("#") else raw
        return tuple(int(hex_value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) == 3:
        channels = [float(part) for part in parts]
        if any(channel < 0 for channel in channels):
            raise ValueError(f"Color channels must be non-negative: {value}")
        if any(channel > 1 for channel in channels):
            if any(channel > 255 for channel in channels):
                raise ValueError(f"RGB color channels must be <= 255: {value}")
            channels = [channel / 255 for channel in channels]
        return tuple(channels)
    raise ValueError(f"Unsupported color value: {value}")


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in rgb)


def format_rgb(rgb: tuple[float, float, float]) -> str:
    return " ".join(f"{channel:.3f}" for channel in rgb)


def render_colors(args: argparse.Namespace) -> dict:
    negative = parse_color(args.negative_color)
    positive = parse_color(args.positive_color)
    return {
        "negative": {"input": args.negative_color, "hex": rgb_to_hex(negative), "rgb": negative},
        "positive": {"input": args.positive_color, "hex": rgb_to_hex(positive), "rgb": positive},
    }


def orbital_list_for_multiwfn(orbitals: list[dict]) -> str:
    seen: list[int] = []
    for orbital in orbitals:
        number = int(orbital["number"])
        if number not in seen:
            seen.append(number)
    return ",".join(str(number) for number in seen)


def default_multiwfn_recipe(outdir: Path, orbitals: list[dict]) -> Path:
    recipe = outdir / "multiwfn_orbitals.inp"
    write_text(
        recipe,
        "\n".join(
            [
                "200",
                "3",
                orbital_list_for_multiwfn(orbitals),
                "3",
                "1",
                "0",
                "q",
                "",
            ]
        ),
    )
    write_text(
        outdir / "multiwfn_orbitals_recipe_note.txt",
        "\n".join(
            [
                "Default recipe target: generate separate orbital cube files, e.g. orb000045.cub.",
                "Menu numbers are version-sensitive. If this fails, edit multiwfn_orbitals.inp",
                "or pass --recipe with a locally confirmed Multiwfn input sequence.",
                "",
            ]
        ),
    )
    return recipe


def run_command(
    command: list[str],
    cwd: Path,
    log_path: Path,
    timeout: int,
    env_updates: dict[str, str] | None = None,
) -> dict:
    env = os.environ.copy()
    if env_updates:
        env.update({key: value for key, value in env_updates.items() if value})
        if env_updates.get("VMDDIR"):
            env["PATH"] = env_updates["VMDDIR"] + os.pathsep + env.get("PATH", "")
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n\n")
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
            return {"returncode": proc.returncode, "log": str(log_path)}
        except subprocess.TimeoutExpired:
            log.write(f"\nTIMEOUT after {timeout} seconds\n")
            return {"returncode": None, "timeout": True, "log": str(log_path)}


def run_multiwfn(
    args: argparse.Namespace,
    tools: dict,
    selected: dict,
    orbitals: list[dict],
    outdir: Path,
) -> dict:
    missing = [orbital for orbital in orbitals if orbital["label"] not in selected["orbital_cubes"]]
    if not missing:
        return {"skipped": True, "reason": "precomputed orbital cubes selected"}
    if not selected.get("wavefunction"):
        return {
            "skipped": True,
            "reason": "no wavefunction file selected",
            "missing_orbitals": [orbital["label"] for orbital in missing],
        }
    if not tools.get("multiwfn"):
        return {
            "skipped": True,
            "reason": "Multiwfn executable not found",
            "missing_orbitals": [orbital["label"] for orbital in missing],
        }

    recipe = expand(args.recipe) if args.recipe else default_multiwfn_recipe(outdir, missing)
    log_path = outdir / "multiwfn_orbitals.log"
    command = [tools["multiwfn"], str(selected["wavefunction"])]
    result = {
        "command": command,
        "recipe": str(recipe),
        "log": str(log_path),
        "target_orbitals": [{"label": o["label"], "number": o["number"]} for o in missing],
    }
    if not args.execute:
        result["skipped"] = True
        result["reason"] = "dry run"
        return result

    env_updates = {}
    if tools.get("multiwfnpath"):
        env_updates["Multiwfnpath"] = tools["multiwfnpath"]
    with recipe.open("r", encoding="utf-8") as recipe_handle, log_path.open(
        "w", encoding="utf-8"
    ) as log:
        log.write("$ " + " ".join(command) + f" < {recipe}\n\n")
        try:
            proc = subprocess.run(
                command,
                cwd=str(outdir),
                stdin=recipe_handle,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=args.timeout,
                check=False,
                env={**os.environ.copy(), **env_updates},
            )
            result["returncode"] = proc.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\nTIMEOUT after {args.timeout} seconds\n")
            result["returncode"] = None
            result["timeout"] = True
    return result


def refresh_orbital_cubes(outdir: Path, selected: dict, orbitals: list[dict]) -> None:
    cubes = list(outdir.glob("*.cube")) + list(outdir.glob("*.cub"))
    for cube in cubes:
        matched = match_cube_to_orbital(cube, orbitals)
        if matched and matched["label"] not in selected["orbital_cubes"]:
            selected["orbital_cubes"][matched["label"]] = cube.resolve()


def vector_length(v: tuple[float, float, float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = vector_length(v)
    if length == 0:
        return (0.0, 0.0, 1.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def parse_axis(value: str | None) -> tuple[float, float, float] | None:
    if not value:
        return None
    token = value.strip().lower()
    axes = {
        "x": (1.0, 0.0, 0.0),
        "+x": (1.0, 0.0, 0.0),
        "-x": (-1.0, 0.0, 0.0),
        "y": (0.0, 1.0, 0.0),
        "+y": (0.0, 1.0, 0.0),
        "-y": (0.0, -1.0, 0.0),
        "z": (0.0, 0.0, 1.0),
        "+z": (0.0, 0.0, 1.0),
        "-z": (0.0, 0.0, -1.0),
    }
    if token in axes:
        return axes[token]
    parts = [part.strip() for part in value.split(",")]
    if len(parts) == 3:
        return normalize((float(parts[0]), float(parts[1]), float(parts[2])))
    raise ValueError(f"Invalid axis specification: {value}")


def read_xyz(path: Path) -> list[tuple[float, float, float]]:
    lines = path.read_text(errors="ignore").splitlines()
    start = 2 if lines and lines[0].strip().isdigit() else 0
    coords = []
    for line in lines[start:]:
        parts = line.split()
        if len(parts) >= 4:
            try:
                coords.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                continue
    return coords


def read_pdb(path: Path) -> list[tuple[float, float, float]]:
    coords = []
    for line in path.read_text(errors="ignore").splitlines():
        if line.startswith(("ATOM", "HETATM")) and len(line) >= 54:
            try:
                coords.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
            except ValueError:
                continue
    return coords


def read_mol(path: Path) -> list[tuple[float, float, float]]:
    lines = path.read_text(errors="ignore").splitlines()
    if len(lines) < 4:
        return []
    try:
        atom_count = int(lines[3][0:3])
    except ValueError:
        return []
    coords = []
    for line in lines[4 : 4 + atom_count]:
        parts = line.split()
        if len(parts) >= 4:
            try:
                coords.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                continue
    return coords


def read_mol2(path: Path) -> list[tuple[float, float, float]]:
    coords = []
    in_atom = False
    for line in path.read_text(errors="ignore").splitlines():
        if line.startswith("@<TRIPOS>ATOM"):
            in_atom = True
            continue
        if line.startswith("@<TRIPOS>") and in_atom:
            break
        if in_atom:
            parts = line.split()
            if len(parts) >= 5:
                try:
                    coords.append((float(parts[2]), float(parts[3]), float(parts[4])))
                except ValueError:
                    continue
    return coords


def read_cube_atoms(path: Path) -> list[tuple[float, float, float]]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            lines = [next(handle) for _ in range(6)]
            atom_count = abs(int(float(lines[2].split()[0])))
            atom_lines = [next(handle) for _ in range(atom_count)]
    except (OSError, StopIteration, ValueError, IndexError):
        return []
    coords = []
    for line in atom_lines:
        parts = line.split()
        if len(parts) >= 5:
            try:
                coords.append((float(parts[2]), float(parts[3]), float(parts[4])))
            except ValueError:
                continue
    return coords


def read_coordinates(selected: dict, orbitals: list[dict]) -> list[tuple[float, float, float]]:
    paths: list[Path] = []
    if selected.get("structure"):
        paths.append(Path(selected["structure"]))
    for orbital in orbitals:
        cube = selected["orbital_cubes"].get(orbital["label"])
        if cube:
            paths.append(Path(cube))
            break
    for path in paths:
        suffix = path.suffix.lower()
        try:
            if suffix == ".xyz":
                coords = read_xyz(path)
            elif suffix in {".pdb"}:
                coords = read_pdb(path)
            elif suffix in {".mol", ".sdf"}:
                coords = read_mol(path)
            elif suffix == ".mol2":
                coords = read_mol2(path)
            elif suffix in CUBE_EXTS:
                coords = read_cube_atoms(path)
            else:
                coords = []
        except OSError:
            coords = []
        if len(coords) >= 2:
            return coords
    return []


def mat_vec_mul(matrix: list[list[float]], vector: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
        matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2],
    )


def power_iteration(matrix: list[list[float]], seed: tuple[float, float, float]) -> tuple[float, tuple[float, float, float]]:
    vector = normalize(seed)
    for _ in range(32):
        vector = normalize(mat_vec_mul(matrix, vector))
    value = dot(vector, mat_vec_mul(matrix, vector))
    return value, vector


def pca_axes(coords: list[tuple[float, float, float]]) -> list[tuple[float, tuple[float, float, float]]]:
    if len(coords) < 2:
        return [
            (3.0, (1.0, 0.0, 0.0)),
            (2.0, (0.0, 1.0, 0.0)),
            (1.0, (0.0, 0.0, 1.0)),
        ]
    center = tuple(sum(coord[i] for coord in coords) / len(coords) for i in range(3))
    shifted = [(x - center[0], y - center[1], z - center[2]) for x, y, z in coords]
    cov = [[0.0, 0.0, 0.0] for _ in range(3)]
    for coord in shifted:
        for i in range(3):
            for j in range(3):
                cov[i][j] += coord[i] * coord[j] / len(shifted)
    first_value, first_vec = power_iteration(cov, (1.0, 0.7, 0.2))
    deflated = [
        [cov[i][j] - first_value * first_vec[i] * first_vec[j] for j in range(3)]
        for i in range(3)
    ]
    second_value, second_vec = power_iteration(deflated, (0.2, 1.0, 0.6))
    third_vec = normalize(cross(first_vec, second_vec))
    third_value = dot(third_vec, mat_vec_mul(cov, third_vec))
    axes = [(first_value, first_vec), (second_value, second_vec), (third_value, third_vec)]
    return sorted(axes, key=lambda item: item[0], reverse=True)


def view_matrix(direction: tuple[float, float, float], up: tuple[float, float, float]) -> list[list[float]]:
    z_axis = normalize(direction)
    if abs(dot(z_axis, normalize(up))) > 0.95:
        up = (0.0, 1.0, 0.0) if abs(z_axis[1]) < 0.9 else (1.0, 0.0, 0.0)
    x_axis = normalize(cross(up, z_axis))
    y_axis = normalize(cross(z_axis, x_axis))
    return [
        [x_axis[0], x_axis[1], x_axis[2], 0.0],
        [y_axis[0], y_axis[1], y_axis[2], 0.0],
        [z_axis[0], z_axis[1], z_axis[2], 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def matrix_tcl(matrix: list[list[float]]) -> str:
    rows = ["{" + " ".join(f"{value:.8f}" for value in row) + "}" for row in matrix]
    return "{{" + " ".join(rows) + "}}"


def compute_views(args: argparse.Namespace, selected: dict, orbitals: list[dict]) -> dict:
    coords = read_coordinates(selected, orbitals)
    axes = pca_axes(coords)
    long_axis = axes[0][1]
    mid_axis = axes[1][1]
    short_axis = axes[2][1]
    front_dir = parse_axis(args.front_axis) or short_axis
    side_dir = parse_axis(args.side_axis) or mid_axis
    front_up = long_axis
    side_up = short_axis if abs(dot(normalize(side_dir), normalize(short_axis))) < 0.9 else long_axis
    return {
        "front": {
            "direction": front_dir,
            "up": front_up,
            "matrix": view_matrix(front_dir, front_up),
        },
        "side": {
            "direction": side_dir,
            "up": side_up,
            "matrix": view_matrix(side_dir, side_up),
        },
        "coordinate_count": len(coords),
        "pca_axes": [{"variance": value, "axis": axis} for value, axis in axes],
    }


def choose_renderer(args: argparse.Namespace, tools: dict) -> str | None:
    if args.renderer != "auto":
        return args.renderer if tools.get(args.renderer) else None
    if tools.get("vmd"):
        return "vmd"
    if tools.get("chimerax"):
        return "chimerax"
    return None


def write_vmd_script(
    args: argparse.Namespace,
    tools: dict,
    selected: dict,
    orbital: dict,
    view_name: str,
    view: dict,
    outdir: Path,
) -> tuple[Path, Path, Path, Path | None]:
    cube = Path(selected["orbital_cubes"][orbital["label"]])
    structure = selected.get("structure")
    safe = orbital["safe"]
    scene = outdir / f"{safe}_{view_name}.dat" if tools.get("tachyon") else None
    tga = outdir / f"{safe}_{view_name}.tga"
    png = outdir / f"{safe}_{view_name}.png"
    script = outdir / f"render_{safe}_{view_name}.tcl"
    iso = args.isovalue
    matrix = matrix_tcl(view["matrix"])
    colors = render_colors(args)
    negative_rgb = format_rgb(tuple(colors["negative"]["rgb"]))
    positive_rgb = format_rgb(tuple(colors["positive"]["rgb"]))
    lines = [
        "display projection Orthographic",
        "display depthcue off",
        "axes location Off",
        "color Display Background white",
        "display ambientocclusion on",
        "display shadows on",
        f"color change rgb 0 {negative_rgb}",
        f"color change rgb 1 {positive_rgb}",
        "material change ambient AOShiny 0.25",
        "material change diffuse AOShiny 0.65",
        "material change specular AOShiny 0.20",
    ]
    if structure:
        lines.append(f"mol new {{{structure}}} waitfor all")
        lines.append(f"mol addfile {{{cube}}} type cube waitfor all")
    else:
        lines.append(f"mol new {{{cube}}} type cube waitfor all")
    lines.extend(
        [
            "mol delrep 0 top",
            "mol representation CPK 0.85 0.30 24 18",
            "mol color Element",
            "mol selection all",
            "mol material AOShiny",
            "mol addrep top",
            f"mol representation Isosurface {iso} 0 0 0 1 1",
            "mol color ColorID 1",
            "mol selection all",
            "mol material AOShiny",
            "mol addrep top",
            f"mol representation Isosurface -{iso} 0 0 0 1 1",
            "mol color ColorID 0",
            "mol selection all",
            "mol material AOShiny",
            "mol addrep top",
            "display resetview",
            f"molinfo top set rotate_matrix {matrix}",
            "scale by 1.15",
            f"render Tachyon {{{scene}}}" if scene else f"render TachyonInternal {{{tga}}}",
            "quit",
        ]
    )
    write_text(script, "\n".join(lines) + "\n")
    return script, tga, png, scene


def chimerax_turn_commands(direction: tuple[float, float, float]) -> list[str]:
    x, y, z = normalize(direction)
    axis = max(((abs(x), "x", x), (abs(y), "y", y), (abs(z), "z", z)), key=lambda item: item[0])
    name, sign = axis[1], axis[2]
    if name == "z":
        return [] if sign >= 0 else ["turn y 180"]
    if name == "x":
        return ["turn y 90"] if sign >= 0 else ["turn y -90"]
    return ["turn x -90"] if sign >= 0 else ["turn x 90"]


def write_chimerax_script(
    args: argparse.Namespace,
    selected: dict,
    orbital: dict,
    view_name: str,
    view: dict,
    outdir: Path,
) -> tuple[Path, Path]:
    cube = Path(selected["orbital_cubes"][orbital["label"]])
    structure = selected.get("structure")
    safe = orbital["safe"]
    png = outdir / f"{safe}_{view_name}.png"
    script = outdir / f"render_{safe}_{view_name}.cxc"
    colors = render_colors(args)
    negative_hex = colors["negative"]["hex"]
    positive_hex = colors["positive"]["hex"]
    lines = [
        "set bgColor white",
        "graphics silhouettes true",
        "lighting soft",
        "camera ortho",
    ]
    model_index = 1
    if structure:
        lines.append(f"open {structure}")
        model_index += 1
    cube_model = f"#{model_index}"
    lines.append(f"open {cube}")
    lines.extend(
        [
            f"volume {cube_model} level -{args.isovalue} color {negative_hex} level {args.isovalue} color {positive_hex} step 1",
            "hide axes",
            "view",
        ]
    )
    lines.extend(chimerax_turn_commands(view["direction"]))
    lines.extend(
        [
            f"save {png} width {args.width} height {args.height} supersample 3",
            "exit",
        ]
    )
    write_text(script, "\n".join(lines) + "\n")
    return script, png


def converter_command(source: Path, target: Path) -> list[str] | None:
    if shutil.which("magick"):
        return ["magick", str(source), str(target)]
    if shutil.which("convert"):
        return ["convert", str(source), str(target)]
    if platform.system().lower() == "darwin" and shutil.which("sips"):
        return ["sips", "-s", "format", "png", str(source), "--out", str(target)]
    return None


def png_size(path: Path) -> tuple[int, int] | None:
    if not path.exists() or path.stat().st_size < 100:
        return None
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", header[16:24])


def render_orbitals(
    args: argparse.Namespace,
    tools: dict,
    selected: dict,
    orbitals: list[dict],
    views: dict,
    outdir: Path,
) -> dict:
    renderer = choose_renderer(args, tools)
    if not renderer:
        return {"skipped": True, "reason": "no requested renderer executable found"}

    rendered = []
    missing = []
    for orbital in orbitals:
        if orbital["label"] not in selected["orbital_cubes"]:
            missing.append(orbital["label"])
            continue
        for view_name in ("front", "side"):
            view = views[view_name]
            if renderer == "vmd":
                script, tga, png, scene = write_vmd_script(
                    args, tools, selected, orbital, view_name, view, outdir
                )
                command = [tools["vmd"], "-dispdev", "text", "-e", str(script)]
                log_path = outdir / f"vmd_{orbital['safe']}_{view_name}.log"
                item = {
                    "orbital": orbital["label"],
                    "number": orbital["number"],
                    "view": view_name,
                    "renderer": renderer,
                    "script": str(script),
                    "scene": str(scene) if scene else None,
                    "intermediate": str(tga),
                    "output": str(png),
                    "command": command,
                    "log": str(log_path),
                }
                if args.execute:
                    result = run_command(
                        command,
                        outdir,
                        log_path,
                        args.timeout,
                        {"VMDDIR": tools.get("vmd_home")} if tools.get("vmd_home") else None,
                    )
                    item.update(result)
                    if scene and scene.exists() and tools.get("tachyon"):
                        tachyon_log = outdir / f"tachyon_{orbital['safe']}_{view_name}.log"
                        tachyon_command = [
                            tools["tachyon"],
                            str(scene),
                            "-aasamples",
                            "12",
                            "-format",
                            "TARGA",
                            "-res",
                            str(args.width),
                            str(args.height),
                            "-o",
                            str(tga),
                        ]
                        item["tachyon_command"] = tachyon_command
                        item["tachyon"] = run_command(tachyon_command, outdir, tachyon_log, args.timeout)
                    convert = converter_command(tga, png)
                    if tga.exists() and convert:
                        conv_log = outdir / f"convert_{orbital['safe']}_{view_name}.log"
                        item["convert_command"] = convert
                        item["convert"] = run_command(convert, outdir, conv_log, args.timeout)
                    item["qa"] = {
                        "png_exists": png.exists(),
                        "png_size": png_size(png),
                        "png_bytes": png.stat().st_size if png.exists() else 0,
                        "tga_exists": tga.exists(),
                        "tga_bytes": tga.stat().st_size if tga.exists() else 0,
                    }
                else:
                    item["skipped"] = True
                    item["reason"] = "dry run"
                rendered.append(item)
            else:
                script, png = write_chimerax_script(args, selected, orbital, view_name, view, outdir)
                command = [tools["chimerax"], "--offscreen", "--script", str(script)]
                log_path = outdir / f"chimerax_{orbital['safe']}_{view_name}.log"
                item = {
                    "orbital": orbital["label"],
                    "number": orbital["number"],
                    "view": view_name,
                    "renderer": renderer,
                    "script": str(script),
                    "output": str(png),
                    "command": command,
                    "log": str(log_path),
                }
                if args.execute:
                    item.update(run_command(command, outdir, log_path, args.timeout))
                    item["qa"] = {
                        "png_exists": png.exists(),
                        "png_size": png_size(png),
                        "png_bytes": png.stat().st_size if png.exists() else 0,
                    }
                else:
                    item["skipped"] = True
                    item["reason"] = "dry run"
                rendered.append(item)
    return {"renderer": renderer, "items": rendered, "missing_orbitals": missing}


def write_summary(outdir: Path, manifest: dict) -> Path:
    path = outdir / "summary.md"
    lines = [
        "# Molecular Orbital Visualization Summary",
        "",
        f"- Execute: `{manifest['execute']}`",
        f"- Renderer: `{manifest['render'].get('renderer', 'none')}`",
        f"- Wavefunction: `{manifest['selected'].get('wavefunction')}`",
        f"- Structure: `{manifest['selected'].get('structure')}`",
        "",
        "## Orbitals",
        "",
        "| Label | Number | Cube | Front | Side |",
        "|---|---:|---|---|---|",
    ]
    outputs: dict[tuple[str, str], str] = {}
    for item in manifest["render"].get("items", []):
        outputs[(item["orbital"], item["view"])] = item.get("output", "")
    cubes = manifest["selected"].get("orbital_cubes", {})
    for orbital in manifest["orbitals"]:
        label = orbital["label"]
        lines.append(
            f"| {label} | {orbital['number']} | `{cubes.get(label, '')}` | `{outputs.get((label, 'front'), '')}` | `{outputs.get((label, 'side'), '')}` |"
        )
    if manifest.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in manifest["warnings"]:
            lines.append(f"- {warning}")
    write_text(path, "\n".join(lines) + "\n")
    return path


def as_jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [as_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: as_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [as_jsonable(item) for item in value]
    return value


def main() -> int:
    try:
        args = parse_args()
        orbitals = parse_orbitals(args.MO, args.homo)
        views_placeholder_error = None
        parse_axis(args.front_axis)
        parse_axis(args.side_axis)
        colors = render_colors(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    outdir = make_outdir(args)
    tools = discover_tools(args)
    selected = discover_files(args, orbitals)
    warnings: list[str] = []
    if not selected.get("wavefunction") and not selected.get("orbital_cubes"):
        warnings.append("No wavefunction file or matching orbital cube was selected.")
    if not tools.get("multiwfn") and any(o["label"] not in selected["orbital_cubes"] for o in orbitals):
        warnings.append("Multiwfn was not found and at least one requested orbital cube is missing.")
    if not tools.get("vmd") and not tools.get("chimerax"):
        warnings.append("Neither VMD nor ChimeraX was found.")
    if selected.get("unmatched_explicit_cubes"):
        warnings.append("Some explicit cube files could not be matched to requested orbitals.")

    multiwfn_result = run_multiwfn(args, tools, selected, orbitals, outdir)
    refresh_orbital_cubes(outdir, selected, orbitals)
    views = compute_views(args, selected, orbitals)
    render_result = render_orbitals(args, tools, selected, orbitals, views, outdir)
    if render_result.get("missing_orbitals"):
        warnings.append(
            "No cube file was available for: " + ", ".join(render_result["missing_orbitals"])
        )
    if args.execute:
        failed_images = []
        for item in render_result.get("items", []):
            output = Path(item.get("output", ""))
            intermediate = Path(item.get("intermediate", ""))
            if not output.exists() and not intermediate.exists():
                failed_images.append(f"{item.get('orbital')} {item.get('view')}")
        if failed_images:
            warnings.append("Rendering did not create image files for: " + ", ".join(failed_images))

    manifest = {
        "task": "molecular orbital visualization",
        "execute": args.execute,
        "workdir": str(expand(args.workdir)),
        "outdir": str(outdir),
        "tools": tools,
        "orbitals": orbitals,
        "selected": selected,
        "parameters": {
            "renderer": args.renderer,
            "isovalue": args.isovalue,
            "colors": colors,
            "front_axis": args.front_axis,
            "side_axis": args.side_axis,
            "width": args.width,
            "height": args.height,
        },
        "views": views,
        "multiwfn": multiwfn_result,
        "render": render_result,
        "warnings": warnings,
    }
    manifest_path = outdir / "manifest.json"
    summary_path = write_summary(outdir, as_jsonable(manifest))
    manifest["summary"] = str(summary_path)
    manifest_path.write_text(json.dumps(as_jsonable(manifest), indent=2), encoding="utf-8")
    print(json.dumps(as_jsonable({"manifest": manifest_path, "summary": summary_path, "warnings": warnings}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
