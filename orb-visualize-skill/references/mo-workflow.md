# MO Workflow

Use this reference for `--MO` molecular orbital visualization tasks.

## User trigger

Treat these as MO visualization requests:

- The prompt contains `--MO`.
- The user asks for HOMO, LUMO, frontier orbital, molecular orbital, MO isosurface, orbital cube, or orbital front/side views.
- The user provides orbital `.cube` files and asks for publication-style figures.

## Orbital specification

Accept comma-separated orbital expressions:

- Absolute numbers: `45`, `46`
- Frontier labels: `HOMO`, `LUMO`
- Relative frontier labels: `HOMO-1`, `HOMO+1`, `LUMO+1`, `LUMO-1`

Require `--homo N` whenever any HOMO/LUMO expression appears. Do not infer the HOMO index in v1.

## Discovery policy

Search in this order:

1. Explicit `--input`, `--structure`, or `--cube` paths.
2. The current user project directory passed as `--workdir`.
3. Additional user-provided directories passed as `--search-root`.
4. Home-directory search only when the user explicitly asks for broad local search; keep it bounded with `--search-home --max-depth`.

Avoid searching the entire filesystem by default.

## File priority

Prefer wavefunction sources in this order when Multiwfn is needed:

1. `.fchk`, `.fch`
2. `.wfx`
3. `.wfn`
4. `.molden`, `.mwfn`

Prefer precomputed orbital cube files when filenames identify the requested orbital:

- `orb000045.cub`, `orb45.cube`, `mo45.cub`
- `HOMO.cub`, `LUMO.cub`, `HOMO-1.cube`

If a cube cannot be matched to a requested orbital, keep it as a candidate in `manifest.json` and do not use it silently.

## View policy

Default to automatic front/side views based on molecular coordinates:

- Front view: look down the smallest-variance molecular axis, usually the face-on direction for planar molecules.
- Side view: look down the middle-variance axis.
- Use the largest-variance axis as the preferred up direction when it is not parallel to the view direction.

If the user supplies `--front-axis` or `--side-axis`, use those vectors instead.

## Delivery policy

Return:

- The final front and side image paths for each requested orbital.
- The manifest path.
- The input file and orbital index mapping used.
- The renderer chosen.
- Warnings about missing tools, missing cube files, unexecuted dry runs, or unvalidated Multiwfn recipe compatibility.
