---
name: input-skill
description: Generate Gaussian and ORCA quantum-chemistry input files from user-provided SMILES strings using RDKit for single-conformer 3D structure generation, Multiwfn for geometry injection, resource-aware templates, and a curated benchmark rule library. Use when the user asks for Gaussian .gjf/.com or ORCA .inp input generation, SMILES-to-input workflows, automatic method/basis recommendation, or computational task setup with cores, memory, charge, multiplicity, and task type.
---

# Input Skill

Use this skill to turn a SMILES string into selected Gaussian and/or ORCA input files with an auditable method/basis recommendation.

## Required Inputs

Always collect these before running the pipeline:

- SMILES string.
- Output program: `gaussian`, `orca`, or `both`.
- Task: `sp`, `opt`, `freq`, `opt-freq`, `tddft`, `nmr`, `interaction-sp`, or `high-accuracy-sp`.
- Number of CPU cores.
- Total memory, for example `8GB` or `64000MB`.
- Net charge.
- Spin multiplicity.

Do not silently infer charge or multiplicity from SMILES. You may mention the formal charge after generation if RDKit reports a mismatch.

When the user has not chosen a program, ask whether they want Gaussian only, ORCA only, or both. Recommend `both` when they are comparing engines or preparing a portable starting point.

## Quick Start

If RDKit is missing, ask the user before running setup:

```bash
python3 skills/input-skill/scripts/input_pipeline.py --setup
```

Ask interactively for missing inputs:

```bash
python3 skills/input-skill/scripts/input_pipeline.py --interactive
```

Generate both Gaussian and ORCA inputs:

```bash
python3 skills/input-skill/scripts/input_pipeline.py \
  --smiles 'c1ccccc1' \
  --task opt-freq \
  --cores 4 \
  --memory 8GB \
  --charge 0 \
  --multiplicity 1 \
  --program both
```

Generate only one program by changing `--program` to `gaussian` or `orca`.

Use `--name <basename>` to control output filenames. Use `--workdir <dir>` to choose where the timestamped `input-skill-run/` directory is created.

## Workflow

1. Read `references/benchmark-library.yml` when you need to explain or audit method/basis selection.
2. Run `scripts/input_pipeline.py --setup` only after the user approves installing RDKit into the skill-local `.venv`.
3. Ask the user for any missing required inputs, especially the output program choice.
4. Run the pipeline with all required inputs. It generates a single RDKit ETKDGv3 conformer and optimizes it with MMFF when available, otherwise UFF.
5. Prefer normal Multiwfn generation. The pipeline writes `structure.xyz` and only the selected program templates, then drives Multiwfn `gi` and/or `oi -> -100` template injection.
6. Return the generated `.gjf` and/or `.inp`, `recommendation.md`, and `manifest.json` paths. Mention any warnings from `manifest.json`.

## Resource Semantics

Interpret user memory as total job memory.

- Gaussian receives `%nprocshared=<cores>` and `%mem=<total memory>`.
- ORCA receives `%pal nprocs <cores> end` and `%maxcore floor(total_MB * 0.75 / cores)`.

If per-core ORCA memory is below 256 MB, report the warning and ask the user to increase total memory or reduce cores before serious production runs.

## Output Contract

The pipeline writes a timestamped output directory containing:

- `source.smiles`
- `structure.xyz`
- `template.gjf` and `<name>.gjf` when Gaussian is selected.
- `template.orca.inp` and `<name>.inp` when ORCA is selected.
- `recommendation.md`
- `manifest.json`
- `multiwfn_gaussian.log` and/or `multiwfn_orca.log`

The manifest records inputs, RDKit version, random seed, charge/multiplicity, resources, selected benchmark rule, citations, Multiwfn path, commands, outputs, and warnings.

## Scientific Guardrails

- Treat generated 3D geometry as a starting structure, not a validated conformational search.
- Warn on unassigned stereocenters, formal-charge mismatch, transition metals, low memory, and Multiwfn fallback generation.
- For transition-metal or unusual spin-state systems, do not present the rule-library choice as generally benchmarked.
- For `high-accuracy-sp`, Gaussian output is a conservative DFT fallback when the selected ORCA method has no Gaussian equivalent.
