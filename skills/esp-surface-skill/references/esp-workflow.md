# ESP Workflow

Use this reference for `--ESP` tasks.

## User trigger

Treat these as ESP requests:

- The prompt contains `--ESP`.
- The user asks for ESP, MEP, molecular electrostatic potential, electrostatic-potential surface, or charge-potential surface maps.
- The user provides ESP/density `.cube` files and asks for a figure.

## Discovery policy

Search in this order:

1. Explicit `--input`, `--structure`, `--esp-cube`, or `--density-cube` paths.
2. The current user project directory passed as `--workdir`.
3. Additional user-provided directories passed as `--search-root`.
4. Home-directory search only when the user explicitly asks for broad local search; keep it bounded with `--search-home --max-depth`.

Avoid searching the entire filesystem by default. It is slow and may traverse unrelated private data.

## File priority

Prefer wavefunction sources in this order when Multiwfn is needed:

1. `.fchk`, `.fch`
2. `.wfx`
3. `.wfn`
4. `.molden`, `.mwfn`
5. `.chk`, `.gbw` only if the local Multiwfn version supports them or the user confirms conversion

Prefer precomputed cube files when names identify them:

- ESP cube keywords: `esp`, `mep`, `electrostatic`, `potential`
- Density cube keywords: `density`, `dens`, `rho`, `electron`

If only one cube exists, inspect the filename and generated manifest before assuming whether it is ESP or density.

## Analysis policy

For publication ESP surface figures, use an electron density isosurface colored by ESP values. A common starting point is an electron density isovalue near `0.001` a.u. and an ESP color range near `-0.05` to `0.05` a.u. Adjust for charged systems, large biomolecules, and outliers.

For charged or highly polar systems, mention that a symmetric fixed range can saturate extremes. If the user asks for quantitative interpretation, include the ESP min/max from Multiwfn logs when available.

## Delivery policy

Return:

- The final image path.
- The manifest path.
- The input file chosen.
- The renderer chosen.
- Any warnings about missing tools, missing cube files, uncertain recipe compatibility, or saturated color ranges.
