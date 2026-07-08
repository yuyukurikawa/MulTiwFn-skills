<h1 align="center">
  <img src="assets/multiwfn-title.svg" alt="MulTiwFn Skill" width="680">
</h1>

<p align="center">
  A Multiwfn-powered Codex skill collection for computational-chemistry wavefunction analysis and publication-ready visualization
</p>

<p align="center">
  <a href="README.md">Chinese README</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#skill-index">Skill Index</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#repository-layout">Repository Layout</a>
</p>

<p align="center">
  <img alt="Codex Skill" src="https://img.shields.io/badge/Codex-Skill-111827">
  <img alt="Multiwfn" src="https://img.shields.io/badge/Multiwfn-required-5BCEFA">
  <img alt="RDKit" src="https://img.shields.io/badge/RDKit-SMILES--to--3D-2563EB">
  <img alt="VMD" src="https://img.shields.io/badge/VMD-rendering-F5A9B8">
  <img alt="ChimeraX" src="https://img.shields.io/badge/ChimeraX-fallback-FFFFFF">
</p>

MulTiwFn is a Codex skill repository for computational-chemistry workflows. It lets Codex generate Gaussian and/or ORCA input files from SMILES, discover local wavefunction files, structure files, and visualization programs, drive Multiwfn to generate cube data, and render manuscript-ready molecular images with VMD/Tachyon or ChimeraX.

The current focus is on three common workflows: SMILES to Gaussian/ORCA input files, electrostatic-potential surface visualization, and front/side views of molecular orbitals such as HOMO and LUMO.

## Installation

### Recommended Codex Installation

Copy the complete skill folders into your Codex skills directory. Do not copy only `SKILL.md`, because each skill also depends on its `scripts/`, `references/`, and `agents/` folders.

```bash
git clone https://github.com/yuyukurikawa/MulTiwFn-skill.git
cd MulTiwFn-skill

mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/input-skill "${CODEX_HOME:-$HOME/.codex}/skills/"
cp -R skills/esp-surface-skill "${CODEX_HOME:-$HOME/.codex}/skills/"
cp -R skills/orb-visualize-skill "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Restart your Codex session after installation, then confirm that the three skills are visible:

```bash
ls "${CODEX_HOME:-$HOME/.codex}/skills"
```

Codex uses the internal names declared in each `SKILL.md`:

```text
$input-skill
$esp-surface-analysis
$molecular-orbital-visualization
```

### Multiwfn

MulTiwFn requires a local Multiwfn installation. Download the version matching your system from the official Multiwfn download page:

- Multiwfn: <https://sobereva.com/multiwfn/download.html>

If `Multiwfn` is not available on `PATH`, pass the executable path explicitly when running a pipeline:

```bash
python3 skills/orb-visualize-skill/scripts/mo_pipeline.py \
  --MO HOMO,LUMO \
  --homo 21 \
  --input benzene.molden.input \
  --multiwfn-bin /path/to/Multiwfn \
  --execute
```

### RDKit

`input-skill` uses RDKit to convert user-provided SMILES strings into a single 3D conformer. The recommended setup installs RDKit into an isolated skill-local virtual environment:

```bash
python3 skills/input-skill/scripts/input_pipeline.py --setup
```

The environment is created at `skills/input-skill/.venv`, so it does not affect your system Python. During normal runs, the pipeline automatically switches to this virtual environment when needed.

### VMD

VMD is the recommended rendering backend for now. It is used with Tachyon to render white-background, orthographic, lit MO/ESP images.

1. Download the appropriate version from the VMD download page: <https://www.ks.uiuc.edu/Development/Download/download.cgi?PackageName=VMD>
2. On macOS, the `.app` bundle is usually placed in `/Applications`.
3. Check whether VMD and Tachyon can be discovered:

```bash
find /Applications -path '*VMD*.app/Contents/vmd*/vmd_*' -o -path '*VMD*.app/Contents/vmd*/tachyon_*'
```

If automatic discovery fails, pass the VMD executable explicitly:

```bash
python3 skills/orb-visualize-skill/scripts/mo_pipeline.py \
  --MO HOMO,LUMO \
  --homo 21 \
  --input benzene.molden.input \
  --renderer vmd \
  --vmd-bin /path/to/vmd \
  --execute
```

### ChimeraX

ChimeraX is the fallback rendering backend. It is useful when VMD is unavailable or when future workflows need more structure-display styles.

1. Install it from the UCSF ChimeraX download page: <https://www.cgl.ucsf.edu/chimerax/download.html>
2. On macOS, the `.app` bundle is usually placed in `/Applications`.
3. Check whether the executable exists:

```bash
find /Applications -path '*ChimeraX*.app/Contents/MacOS/ChimeraX'
```

If automatic discovery fails, pass the ChimeraX executable explicitly:

```bash
python3 skills/esp-surface-skill/scripts/esp_pipeline.py \
  --ESP \
  --input benzene.molden.input \
  --renderer chimerax \
  --chimerax-bin /path/to/ChimeraX \
  --execute
```

## Skill Index

| Skill | Triggers | Best For | Main Outputs |
| --- | --- | --- | --- |
| `input-skill` | SMILES, Gaussian input, ORCA input, `--smiles` | Generate a 3D structure from SMILES, ask for missing parameters, recommend a method/basis from a curated benchmark library, and selectively output Gaussian, ORCA, or both input files | `structure.xyz`, selected `<name>.gjf`/`<name>.inp`, `recommendation.md`, `manifest.json` |
| `esp-surface-analysis` | `--ESP`, ESP, MEP, electrostatic-potential surface | Generate an ESP-colored molecular surface from `.fchk`, `.molden`, `.wfn`, `.wfx`, cube, and related files | `density.cub`, `totesp.cub`, rendering scripts, `esp_vmd.png` or ChimeraX PNG, `manifest.json` |
| `molecular-orbital-visualization` | `--MO`, HOMO, LUMO, molecular orbital, MO cube | Generate orbital cube files and deliver front/side views for selected orbitals | `<orbital>.cub`, `<orbital>_front.png`, `<orbital>_side.png`, rendering scripts, `summary.md`, `manifest.json` |

## Quick Start

### Use input-skill in Codex

```text
Use $input-skill. SMILES is c1ccccc1, task is opt-freq, cores 4, memory 8GB, charge 0, multiplicity 1. Please ask me whether to generate Gaussian, ORCA, or both.
```

If a prompt is missing `SMILES`, task type, core count, total memory, charge, spin multiplicity, or output program, the skill asks for the missing information before writing the final files.

### Run the input pipeline directly

Interactive mode asks for missing information, including whether to generate Gaussian only, ORCA only, or both:

```bash
python3 skills/input-skill/scripts/input_pipeline.py --interactive
```

Non-interactive runs can specify the output program explicitly:

```bash
python3 skills/input-skill/scripts/input_pipeline.py \
  --smiles 'c1ccccc1' \
  --task opt-freq \
  --cores 4 \
  --memory 8GB \
  --charge 0 \
  --multiplicity 1 \
  --program both \
  --name benzene
```

Common options:

- `--setup`: install RDKit into `skills/input-skill/.venv`.
- `--interactive`: ask for missing inputs, useful for quickly building a calculation from a SMILES string.
- `--program gaussian|orca|both`: generate Gaussian only, ORCA only, or both. In interactive mode, the pipeline asks when this is omitted. In non-interactive mode, omission defaults to `both`.
- `--task sp|opt|freq|opt-freq|tddft|nmr|interaction-sp|high-accuracy-sp`: choose the calculation task.
- `--cores 8 --memory 32GB`: set CPU cores and total job memory. ORCA `%maxcore` is computed automatically.
- `--no-multiwfn`: inject geometry with local templates only, useful for quick checks or when Multiwfn is unavailable.

### Use the MO skill in Codex

```text
Use $molecular-orbital-visualization --MO HOMO,LUMO --homo 21, input file is benzene.molden.input
```

### Run the MO pipeline directly

```bash
python3 skills/orb-visualize-skill/scripts/mo_pipeline.py \
  --MO HOMO,LUMO \
  --homo 21 \
  --input benzene.molden.input \
  --execute
```

Common options:

- `--MO HOMO,LUMO,HOMO-1,LUMO+1`: select orbitals to render.
- `--homo 21`: required when using HOMO/LUMO relative expressions.
- `--structure benzene.xyz`: provide a structure file to help render bonds.
- `--front-axis z --side-axis x`: override front and side view directions.
- `--isovalue 0.03`: set the orbital isosurface value.

### Use the ESP skill in Codex

```text
Use $esp-surface-analysis --ESP, input file is benzene.molden.input
```

### Run the ESP pipeline directly

```bash
python3 skills/esp-surface-skill/scripts/esp_pipeline.py \
  --ESP \
  --input benzene.molden.input \
  --execute
```

Common options:

- `--density-isovalue 0.001`: set the electron-density isosurface value.
- `--esp-range -0.05,0.05`: set the ESP color range in a.u.
- `--renderer vmd`: force VMD/Tachyon rendering.
- `--renderer chimerax`: force ChimeraX rendering.

## Repository Layout

```text
.
├── README.md
├── README.en.md
├── assets/
│   └── multiwfn-title.svg
└── skills/
    ├── input-skill/
    │   ├── SKILL.md
    │   ├── agents/
    │   ├── references/benchmark-library.yml
    │   └── scripts/input_pipeline.py
    ├── esp-surface-skill/
    │   ├── SKILL.md
    │   ├── agents/
    │   ├── references/
    │   └── scripts/esp_pipeline.py
    └── orb-visualize-skill/
        ├── SKILL.md
        ├── agents/
        ├── references/
        └── scripts/mo_pipeline.py
```

## Outputs and Reproducibility

Each pipeline run writes a `manifest.json` recording discovered files, tool paths, actual commands, warnings, and output files. `input-skill` also writes `recommendation.md`, which lists the selected method/basis, rationale, DOI references, and scientific caveats. When rendering fails, first inspect the Multiwfn recipe, VMD/ChimeraX scripts, and logs in the same output directory.

Avoid committing large calculation artifacts to GitHub. The repository `.gitignore` already ignores common ORCA outputs, cube files, `input-skill-run/`, and local test directories.

## Scientific Notes

- The SMILES-to-3D flow in `input-skill` generates only one RDKit conformer. It is suitable for fast input-file scaffolding, not a conformational search.
- `input-skill` does not silently infer charge or spin multiplicity. Confirm `charge` and `multiplicity` before generation.
- Method/basis recommendations come from a curated benchmark library. Complex open-shell, transition-metal, and multi-reference systems still require expert review.
- Molecular-orbital phase is arbitrary. Swapping positive and negative colors for the same orbital does not change its physical meaning.
- When using `HOMO`, `LUMO`, `HOMO-1`, or `LUMO+1`, v1 does not guess the HOMO index automatically. You must provide `--homo N`.
- Multiwfn menu recipes may change between versions. If a real system fails, keep the log and recipe, calibrate them against your current Multiwfn version, and then update the skill.
- ChimeraX offscreen rendering can vary across macOS/OpenGL environments. Prefer VMD/Tachyon for unattended image generation.
