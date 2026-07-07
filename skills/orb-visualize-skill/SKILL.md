---
name: molecular-orbital-visualization
description: Automatic molecular orbital visualization for computational chemistry. Use when the user includes --MO or asks for HOMO, LUMO, orbital number, molecular orbital, MO cube, frontier orbital, or publication-style front/side orbital views from local wavefunction files such as .fchk, .fch, .wfn, .wfx, .molden, .mwfn, .cube, .cub, .xyz, .mol, .sdf, .pdb, or .mol2.
---

# Molecular Orbital Visualization

Use this skill to discover local wavefunction/orbital cube files, run Multiwfn when needed, and render requested molecular orbitals as front and side views.

## Quick Start

For a user request containing `--MO`, run:

```bash
python3 scripts/mo_pipeline.py --MO HOMO,LUMO --homo <HOMO-index> --workdir <user-project-dir> --execute
```

Use `--input <file>` when the user names a wavefunction file. Use `--cube <label=path>` or repeated `--cube <path>` when orbital cube files already exist. Use `--search-root <dir>` repeatedly when the user wants files found outside the current project.

## Workflow

1. Read `references/mo-workflow.md` before running an analysis.
2. Run `scripts/mo_pipeline.py --MO ... --workdir ...` without `--execute` when you need to inspect selected files, orbital indices, and tools first.
3. Run again with `--execute` once the selected inputs and orbital mapping are plausible.
4. If Multiwfn fails to generate cube files, read `references/multiwfn-orbital-recipes.md`, inspect `multiwfn_orbitals.inp` and logs, then patch or rerun with `--recipe <file>`.
5. If rendering fails, read `references/orbital-visualization.md`, inspect the generated `.tcl` or `.cxc` scripts, and rerun with `--renderer vmd` or `--renderer chimerax`.
6. Return the front/side image paths, manifest path, exact commands used, and caveats about orbital numbering or unvalidated recipes.

## Required User Information

Users may provide absolute orbital numbers directly:

```bash
python3 scripts/mo_pipeline.py --MO 45,46 --input molecule.fchk --execute
```

Users may provide frontier labels only when `--homo <N>` is also known:

```bash
python3 scripts/mo_pipeline.py --MO HOMO,LUMO,HOMO-1 --homo 45 --input molecule.fchk --execute
```

Do not infer the HOMO index silently from filenames or logs in v1.

## Output Contract

The pipeline writes an output folder containing:

- `manifest.json` with selected files, discovered tools, orbital mappings, commands, warnings, and outputs.
- `summary.md` with the requested orbitals and generated image paths.
- `multiwfn_orbitals.inp` and `multiwfn_orbitals.log` when Multiwfn is used.
- `render_<orbital>_front.tcl` and `render_<orbital>_side.tcl` for VMD, or `.cxc` scripts for ChimeraX.
- `<orbital>_front.png` and `<orbital>_side.png` when rendering succeeds; VMD may also leave intermediate `.tga` files.

If a dependency or input is missing, report exactly what was discovered and which file, tool, or orbital index is needed next.
