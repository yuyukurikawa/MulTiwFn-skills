---
name: aromatic-skill
description: Multiwfn aromaticity and electron-delocalization workflow skill. Use when the user includes --aromatic or asks for aromaticity, antiaromaticity, NICS, ICSS, HOMA, HOMAc, HOMER, Bird index, multicenter bond order, MCI, AV1245, PDI, FLU, FLU-pi, PLR, ITA aromaticity, Shannon aromaticity, ring critical point properties, ELF/LOL pi analysis, or LOLIPOP from SMILES, structures, wavefunction files, Gaussian NMR outputs, or Multiwfn outputs.
---

# Aromatic Skill

Use this skill to explain and prepare Multiwfn aromaticity analyses, then run or resume the selected workflow when the required files are available.

## Required Behavior

Always start aromaticity requests by giving a concise overview of the available method families unless the user explicitly names a method and asks to skip explanation.

Use `references/aromatic-methods.yml` for method cards, required inputs, outputs, and caveats. Use `references/multiwfn-aromatic-recipes.md` when a generated Multiwfn recipe needs inspection or repair.

## Quick Start

Explain all supported methods and create a dry-run plan:

```bash
python3 skills/aromatic-skill/scripts/aromatic_pipeline.py --aromatic --explain --workdir <project-dir>
```

Prepare a specific workflow:

```bash
python3 skills/aromatic-skill/scripts/aromatic_pipeline.py \
  --aromatic \
  --method homa \
  --input molecule.xyz \
  --ring-atoms 1-6
```

Prepare NICS-1D from SMILES by calling input-skill for a Gaussian NMR template:

```bash
python3 skills/aromatic-skill/scripts/aromatic_pipeline.py \
  --aromatic \
  --method nics-1d \
  --smiles 'c1ccccc1' \
  --charge 0 \
  --multiplicity 1 \
  --ring-atoms 1-6
```

After the user runs the generated Gaussian job, resume with:

```bash
python3 skills/aromatic-skill/scripts/aromatic_pipeline.py \
  --aromatic \
  --method nics-1d \
  --resume-manifest aromatic-skill-run/<run>/manifest.json \
  --gaussian-output NICS_1D.out \
  --ring-atoms 1-6
```

Add `--execute` only when the recipe has no placeholders and a valid Multiwfn input file is available.

## Workflow

1. Run the pipeline with `--aromatic --explain` or read `references/aromatic-methods.yml` to present all methods briefly.
2. Identify the user's target method. If unspecified, ask which method family they want after explaining the options.
3. Inspect provided files. Gaussian NMR outputs containing `GIAO Magnetic shielding tensor` and `Bq` should be treated as NICS/ICSS-ready and the user should be asked whether to continue aromaticity analysis.
4. For SMILES-only requests, call aromatic_pipeline with `--smiles`; it delegates structure/input preparation to `input-skill`. Collect charge and multiplicity first rather than silently inferring them.
5. For ring-dependent analyses, suggest ring candidates when possible, but require user confirmation via `--ring-atoms` before production calculations. Multi-ring systems must never proceed with a silent default ring.
6. For FLU-pi, ELF/LOL-pi, and LOLIPOP, require confirmed `--pi-orbitals`.
7. For NICS/ICSS, use the Gaussian two-stage flow: generate template/Bq input first, wait for the user to run Gaussian, then resume from `.out` or `.log`.
8. Return `aromatic_summary.md`, `manifest.json`, generated recipes, any parsed result files, and warnings.

## Output Contract

Each run writes `aromatic-skill-run/<name>-YYYYMMDD-HHMMSS/` unless `--outdir` is provided.

Expected outputs:

- `method_overview.md`
- `aromatic_plan.md`
- `aromatic_results.json`
- `aromatic_summary.md`
- `manifest.json`
- `multiwfn_aromatic.inp`
- `multiwfn_aromatic.log`
- NICS/ICSS intermediate inputs and parsed text/cube/PDF outputs when available.

Do not claim a numeric result was produced unless `aromatic_results.json` or `manifest.json` records an existing parsed result or a successful Multiwfn execution.

## Scientific Guardrails

- Treat RDKit SMILES geometries as starting structures only.
- Confirm ring atom order follows connectivity for HOMA, Bird, FLU, AV1245, and multicenter methods.
- Confirm pi orbitals explicitly for pi-resolved methods.
- Report that ORCA NMR output parsing is not a v1 target; NICS/ICSS resume expects Gaussian NMR output.
- For topology/fuzzy methods, report partition scheme, critical point, or grid caveats when relevant.
