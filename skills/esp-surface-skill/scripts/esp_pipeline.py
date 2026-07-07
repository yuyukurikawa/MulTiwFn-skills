#!/usr/bin/env python3
"""Discover inputs/tools, run Multiwfn if needed, and render ESP surface figures."""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
from pathlib import Path
import platform
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
    ".chk": 30,
    ".gbw": 30,
}
CUBE_EXTS = {".cube", ".cub"}
STRUCTURE_EXTS = {".xyz", ".mol", ".sdf", ".pdb", ".mol2"}
ESP_KEYS = ("esp", "mep", "electrostatic", "potential")
DENSITY_KEYS = ("density", "dens", "rho", "electron")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ESP surface analysis pipeline for Multiwfn, VMD, and ChimeraX."
    )
    parser.add_argument("--ESP", action="store_true", help="Required ESP task flag.")
    parser.add_argument("--workdir", default=".", help="Primary directory to search.")
    parser.add_argument("--search-root", action="append", default=[], help="Extra search root.")
    parser.add_argument("--search-home", action="store_true", help="Search the user home directory.")
    parser.add_argument("--max-depth", type=int, default=4, help="Maximum recursive search depth.")
    parser.add_argument("--input", help="Wavefunction input file.")
    parser.add_argument("--structure", help="Structure file for rendering.")
    parser.add_argument("--esp-cube", help="Precomputed ESP cube.")
    parser.add_argument("--density-cube", help="Precomputed electron-density cube.")
    parser.add_argument("--outdir", help="Output directory.")
    parser.add_argument("--renderer", choices=("auto", "chimerax", "vmd"), default="auto")
    parser.add_argument("--multiwfn-bin", help="Path to Multiwfn executable.")
    parser.add_argument("--vmd-bin", help="Path to VMD executable.")
    parser.add_argument("--chimerax-bin", help="Path to ChimeraX executable.")
    parser.add_argument("--recipe", help="Custom Multiwfn stdin recipe.")
    parser.add_argument("--density-isovalue", default="0.001", help="Density isosurface value.")
    parser.add_argument("--esp-range", default="-0.05,0.05", help="ESP color range in a.u.")
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
                "/Applications/UCSF ChimeraX*.app/Contents/MacOS/ChimeraX",
            )
        )
        tools["multiwfn"] = tools["multiwfn"] or first_existing(
            (
                "/Users/*/Applications/multiwfn-mac-build/build/Multiwfn",
                "/Users/*/Applications/multiwfn-mac-build/build/multiwfn",
                "/Applications/Multiwfn*/Multiwfn",
                "/usr/local/bin/Multiwfn",
                "/opt/homebrew/bin/Multiwfn",
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
        for candidate in (exe.parent.parent, exe.parent):
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
                tools["vmd"] = str(matches[0].resolve())
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
        base = 60
        if any(key in name for key in ESP_KEYS):
            base += 20
        if any(key in name for key in DENSITY_KEYS):
            base += 15
        return base
    if suffix in STRUCTURE_EXTS:
        return 40
    return 0


def classify_cube(path: Path) -> str:
    name = path.name.lower()
    esp = any(key in name for key in ESP_KEYS)
    density = any(key in name for key in DENSITY_KEYS)
    if esp and not density:
        return "esp"
    if density and not esp:
        return "density"
    if esp:
        return "esp"
    if density:
        return "density"
    return "unknown"


def discover_files(args: argparse.Namespace) -> dict:
    roots = [expand(args.workdir)]
    roots.extend(expand(root) for root in args.search_root)
    if args.search_home:
        roots.append(Path.home().resolve())
    roots = [root for root in roots if root]

    explicit = {
        "wavefunction": expand(args.input),
        "structure": expand(args.structure),
        "esp_cube": expand(args.esp_cube),
        "density_cube": expand(args.density_cube),
    }

    candidates: list[Path] = []
    for root in roots:
        candidates.extend(iter_files(root, args.max_depth))

    wavefunctions = [p for p in candidates if p.suffix.lower() in WAVEFUNCTION_EXTS]
    structures = [p for p in candidates if p.suffix.lower() in STRUCTURE_EXTS]
    cubes = [p for p in candidates if p.suffix.lower() in CUBE_EXTS]

    def best(paths: list[Path]) -> Path | None:
        if not paths:
            return None
        return sorted(paths, key=lambda p: (score_file(p), p.stat().st_mtime), reverse=True)[0]

    esp_cubes = [p for p in cubes if classify_cube(p) == "esp"]
    density_cubes = [p for p in cubes if classify_cube(p) == "density"]

    selected = {
        "wavefunction": explicit["wavefunction"] or best(wavefunctions),
        "structure": explicit["structure"] or best(structures),
        "esp_cube": explicit["esp_cube"] or best(esp_cubes),
        "density_cube": explicit["density_cube"] or best(density_cubes),
    }
    selected["cube_candidates"] = sorted([str(p) for p in cubes], key=str)[:50]
    selected["wavefunction_candidates"] = sorted([str(p) for p in wavefunctions], key=str)[:50]
    selected["structure_candidates"] = sorted([str(p) for p in structures], key=str)[:50]
    return selected


def make_outdir(args: argparse.Namespace) -> Path:
    if args.outdir:
        outdir = expand(args.outdir)
    else:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        outdir = expand(args.workdir) / f"esp-output-{stamp}"
    assert outdir is not None
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def default_multiwfn_recipe(outdir: Path) -> Path:
    recipe = outdir / "multiwfn_esp.inp"
    write_text(
        recipe,
        "\n".join(
            [
                "5",
                "1",
                "2",
                "2",
                "0",
                "5",
                "12",
                "1",
                "2",
                "0",
                "q",
                "",
            ]
        ),
    )
    write_text(
        outdir / "multiwfn_esp_recipe_note.txt",
        "\n".join(
            [
                "Default recipe target: generate density.cub and totesp.cub.",
                "Menu numbers are version-sensitive. If this fails, edit multiwfn_esp.inp",
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


def run_multiwfn(args: argparse.Namespace, tools: dict, selected: dict, outdir: Path) -> dict:
    wavefunction = selected.get("wavefunction")
    if selected.get("esp_cube") and selected.get("density_cube"):
        return {"skipped": True, "reason": "precomputed cubes selected"}
    if not wavefunction:
        return {"skipped": True, "reason": "no wavefunction file selected"}
    if not tools.get("multiwfn"):
        return {"skipped": True, "reason": "Multiwfn executable not found"}

    recipe = expand(args.recipe) if args.recipe else default_multiwfn_recipe(outdir)
    log_path = outdir / "multiwfn_esp.log"
    command = [tools["multiwfn"], str(wavefunction)]
    result = {"command": command, "recipe": str(recipe), "log": str(log_path)}
    if not args.execute:
        result["skipped"] = True
        result["reason"] = "dry run"
        return result

    with recipe.open("r", encoding="utf-8") as recipe_handle, log_path.open(
        "w", encoding="utf-8"
    ) as log:
        log.write("$ " + " ".join(command) + f" < {recipe}\n\n")
        env_updates = {}
        if tools.get("multiwfnpath"):
            env_updates["Multiwfnpath"] = tools["multiwfnpath"]
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


def refresh_cubes(outdir: Path, selected: dict) -> None:
    cubes = list(outdir.glob("*.cube")) + list(outdir.glob("*.cub"))
    esp = selected.get("esp_cube")
    density = selected.get("density_cube")
    for cube in cubes:
        kind = classify_cube(cube)
        if kind == "esp" and not esp:
            selected["esp_cube"] = cube.resolve()
            esp = selected["esp_cube"]
        elif kind == "density" and not density:
            selected["density_cube"] = cube.resolve()
            density = selected["density_cube"]


def parse_range(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise ValueError("--esp-range must look like -0.05,0.05")
    return parts[0], parts[1]


def write_chimerax_script(args: argparse.Namespace, selected: dict, outdir: Path) -> Path:
    esp_min, esp_max = parse_range(args.esp_range)
    structure = selected.get("structure")
    density = selected.get("density_cube")
    esp = selected.get("esp_cube")
    output = outdir / "esp_chimerax.png"
    script = outdir / "render_chimerax.cxc"
    model_index = 1
    structure_model = None
    density_model = None
    esp_model = None
    lines = [
        "set bgColor white",
        "graphics silhouettes true",
        "lighting soft",
        "camera ortho",
    ]
    if structure:
        lines.append(f"open {structure}")
        structure_model = f"#{model_index}"
        model_index += 1
    if density:
        lines.append(f"open {density}")
        density_model = f"#{model_index}"
        model_index += 1
    if esp:
        lines.append(f"open {esp}")
        esp_model = f"#{model_index}"
        model_index += 1
    atom_model = structure_model or density_model
    lines.extend(
        [
            f"volume {density_model} style surface level {args.density_isovalue} color white transparency 15",
            f"color sample {density_model} map {esp_model} palette blue:white:red range {esp_min},{esp_max}",
            "hide atoms",
            f"show {atom_model} atoms",
            f"style {atom_model} ball",
            "view",
            f"save {output} width {args.width} height {args.height} supersample 3",
            "exit",
        ]
    )
    write_text(script, "\n".join(lines) + "\n")
    return script


def write_vmd_script(args: argparse.Namespace, selected: dict, outdir: Path, tools: dict) -> tuple[Path, Path, Path, Path | None]:
    esp_min, esp_max = parse_range(args.esp_range)
    structure = selected.get("structure") or selected.get("density_cube") or selected.get("esp_cube")
    density = selected.get("density_cube")
    esp = selected.get("esp_cube")
    scene = outdir / "esp_vmd.dat" if tools.get("tachyon") else None
    output = outdir / "esp_vmd.tga"
    png = outdir / "esp_vmd.png"
    script = outdir / "render_vmd.tcl"
    lines = [
        "display projection Orthographic",
        "display depthcue off",
        "axes location Off",
        "color Display Background white",
        "display ambientocclusion on",
        "display shadows on",
        "color scale method BWR",
        "color scale midpoint 0.5",
    ]
    if structure:
        lines.append(f"mol new {{{structure}}}")
    if density:
        lines.append(f"mol addfile {{{density}}} type cube waitfor all")
    if esp:
        lines.append(f"mol addfile {{{esp}}} type cube waitfor all")
    lines.extend(
        [
            "mol delrep 0 top",
            "mol representation CPK 1.0 0.3 24 18",
            "mol color Element",
            "mol selection all",
            "mol material AOShiny",
            "mol addrep top",
            f"mol representation Isosurface {args.density_isovalue} 0 0 0 1 1",
            "mol color Volume 1",
            f"mol scaleminmax top 1 {esp_min} {esp_max}",
            "mol material Transparent",
            "mol addrep top",
            "display resetview",
            f"render Tachyon {{{scene}}}" if scene else f"render TachyonInternal {{{output}}}",
            "quit",
        ]
    )
    write_text(script, "\n".join(lines) + "\n")
    return script, output, png, scene


def choose_renderer(args: argparse.Namespace, tools: dict) -> str | None:
    if args.renderer != "auto":
        return args.renderer if tools.get(args.renderer) else None
    if tools.get("vmd"):
        return "vmd"
    if tools.get("chimerax"):
        return "chimerax"
    return None


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


def render(args: argparse.Namespace, tools: dict, selected: dict, outdir: Path) -> dict:
    if not selected.get("esp_cube"):
        return {"skipped": True, "reason": "no ESP cube selected"}
    if not selected.get("density_cube"):
        return {"skipped": True, "reason": "no density cube selected for surface geometry"}
    renderer = choose_renderer(args, tools)
    if not renderer:
        return {"skipped": True, "reason": "no requested renderer executable found"}

    if renderer == "chimerax":
        script = write_chimerax_script(args, selected, outdir)
        output = outdir / "esp_chimerax.png"
        png = output
        command = [tools["chimerax"], "--offscreen", "--script", str(script)]
        log_path = outdir / "chimerax_render.log"
        scene = None
    else:
        script, output, png, scene = write_vmd_script(args, selected, outdir, tools)
        command = [tools["vmd"], "-dispdev", "text", "-e", str(script)]
        log_path = outdir / "vmd_render.log"

    result = {
        "renderer": renderer,
        "script": str(script),
        "scene": str(scene) if scene else None,
        "output": str(output),
        "png": str(png),
        "command": command,
        "log": str(log_path),
    }
    if not args.execute:
        result["skipped"] = True
        result["reason"] = "dry run"
        return result
    env_updates = {"VMDDIR": tools.get("vmd_home")} if renderer == "vmd" and tools.get("vmd_home") else None
    result.update(run_command(command, outdir, log_path, args.timeout, env_updates))
    if renderer == "vmd" and scene and scene.exists() and tools.get("tachyon"):
        tachyon_log = outdir / "tachyon_render.log"
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
            str(output),
        ]
        result["tachyon_command"] = tachyon_command
        result["tachyon"] = run_command(tachyon_command, outdir, tachyon_log, args.timeout)
    if renderer == "vmd":
        convert = converter_command(output, png)
        if output.exists() and convert:
            convert_log = outdir / "convert_render.log"
            result["convert_command"] = convert
            result["convert"] = run_command(convert, outdir, convert_log, args.timeout)
    if output.suffix.lower() == ".png":
        size = png_size(output)
        result["qa"] = {"exists": output.exists(), "png_size": size, "bytes": output.stat().st_size if output.exists() else 0}
    else:
        result["qa"] = {
            "exists": output.exists(),
            "bytes": output.stat().st_size if output.exists() else 0,
            "png_exists": png.exists(),
            "png_size": png_size(png),
            "png_bytes": png.stat().st_size if png.exists() else 0,
        }
    return result


def as_jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: as_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [as_jsonable(item) for item in value]
    return value


def main() -> int:
    args = parse_args()
    if not args.ESP:
        print("This pipeline requires --ESP.", file=sys.stderr)
        return 2

    outdir = make_outdir(args)
    tools = discover_tools(args)
    selected = discover_files(args)
    warnings: list[str] = []
    if not selected.get("esp_cube") and not selected.get("wavefunction"):
        warnings.append("No ESP cube or wavefunction file was selected.")
    if not selected.get("density_cube"):
        warnings.append("No density cube was selected; renderer may need Multiwfn output.")
    if not tools.get("multiwfn") and not selected.get("esp_cube"):
        warnings.append("Multiwfn was not found and no ESP cube is available.")
    if not tools.get("chimerax") and not tools.get("vmd"):
        warnings.append("Neither ChimeraX nor VMD was found.")

    multiwfn_result = run_multiwfn(args, tools, selected, outdir)
    refresh_cubes(outdir, selected)
    render_result = render(args, tools, selected, outdir)
    if selected.get("density_cube"):
        warnings = [warning for warning in warnings if not warning.startswith("No density cube")]
    if selected.get("esp_cube"):
        warnings = [
            warning
            for warning in warnings
            if not warning.startswith("No ESP cube or wavefunction")
            and not warning.startswith("Multiwfn was not found")
        ]
    if args.execute:
        render_png = Path(render_result.get("png") or render_result.get("output") or "")
        render_output = Path(render_result.get("output") or "")
        if render_result.get("renderer") and not render_png.exists() and not render_output.exists():
            warnings.append("Rendering did not create an image file.")

    manifest = {
        "task": "ESP surface analysis",
        "execute": args.execute,
        "workdir": str(expand(args.workdir)),
        "outdir": str(outdir),
        "tools": tools,
        "selected": selected,
        "parameters": {
            "renderer": args.renderer,
            "density_isovalue": args.density_isovalue,
            "esp_range": args.esp_range,
            "width": args.width,
            "height": args.height,
        },
        "multiwfn": multiwfn_result,
        "render": render_result,
        "warnings": warnings,
    }
    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(as_jsonable(manifest), indent=2), encoding="utf-8")
    print(json.dumps(as_jsonable({"manifest": manifest_path, "warnings": warnings}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
