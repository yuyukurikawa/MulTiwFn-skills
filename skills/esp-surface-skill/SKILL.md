---
name: esp-surface-analysis
description: Automatic ESP electrostatic potential surface analysis and figure generation for computational chemistry. Use when the user includes --ESP or asks for ESP/MEP/electrostatic-potential surface analysis, Multiwfn ESP cube generation, or publication-style ESP molecular surface rendering from local wavefunction files such as .fchk, .fch, .wfn, .wfx, .molden, .mwfn, .cube, .cub, .xyz, .mol, .sdf, .pdb, or .mol2.
---

# ESP Surface Analysis

Use this skill to discover local wavefunction/structure files, run Multiwfn when needed, and render ESP-colored molecular surface figures with VMD or ChimeraX.

## Quick Start

For a user request containing `--ESP`, run:

```bash
python3 scripts/esp_pipeline.py --ESP --workdir <user-project-dir> --execute
```

Use `--input <file>` when the user names a wavefunction/cube file. Use `--search-root <dir>` repeatedly when the user wants files found outside the current project.

## Workflow

1. Read `references/esp-workflow.md` before running an analysis.
2. Run `scripts/esp_pipeline.py --ESP --workdir ...` without `--execute` if you need to inspect the selected files and tools first.
3. Run again with `--execute` once the selected inputs are plausible.
4. If Multiwfn fails, read `references/multiwfn-recipes.md`, inspect the generated `multiwfn_*.inp` and logs, then patch or rerun with `--recipe <file>`.
5. If rendering fails, read `references/visualization.md`, inspect the generated `.cxc` or `.tcl`, and rerun with `--renderer chimerax` or `--renderer vmd`.
6. Return the rendered image path, manifest path, exact commands used, and any scientific caveats.

## Tool Selection

Prefer this order:

1. Existing ESP and density cube files: render directly.
2. Wavefunction file plus Multiwfn: generate cube files, then render.
3. ChimeraX renderer: prefer for robust offscreen PNG output and large molecular systems.
4. VMD renderer: prefer when ChimeraX is unavailable or VMD cube styling is requested.

Do not claim that an ESP figure was generated unless `manifest.json` shows a rendered image file that exists and passes the script QA checks.

## Output Contract

The pipeline writes an output folder containing:

- `manifest.json` with selected files, discovered tools, commands, warnings, and outputs.
- `multiwfn_*.inp` and `multiwfn_*.log` when Multiwfn is used.
- `render_chimerax.cxc` or `render_vmd.tcl` when rendering is prepared.
- A rendered image when rendering succeeds, usually PNG from ChimeraX or TGA from VMD.

If a dependency is missing, report exactly what was discovered and which file or program is needed next.
