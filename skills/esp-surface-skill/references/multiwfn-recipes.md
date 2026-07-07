# Multiwfn Recipes

Use this reference when Multiwfn must generate cube files for ESP rendering.

## Version sensitivity

Multiwfn is menu-driven and menu numbers can vary by version and build. Keep recipes in generated `.inp` files and logs so failures are reproducible. If the default recipe fails, inspect `multiwfn_*.log`, update the recipe file, and rerun with:

```bash
python3 scripts/esp_pipeline.py --ESP --input molecule.fchk --recipe fixed_recipe.inp --execute
```

## Target outputs

The rendering pipeline needs:

- One electron density cube for the isosurface geometry.
- One ESP cube for coloring the isosurface.

If the user already has both cubes, skip Multiwfn.

## Default strategy

The bundled script creates a two-pass recipe commonly used for ESP surface plotting:

1. Generate electron density grid data and export it as cube.
2. Generate electrostatic potential grid data and export it as cube.

For many Multiwfn builds, the input sequence is:

```text
5
1
2
2
0
5
12
1
2
0
q
```

Expected output names are usually `density.cub` and `totesp.cub`. Because local Multiwfn menus differ, treat unsuccessful cube generation as a recipe-compatibility problem, not as a failed scientific result.

## Safe execution rules

- Always run Multiwfn in the output directory.
- Always capture stdout/stderr to a log file.
- Always use a timeout.
- Never overwrite the source wavefunction file.
- After execution, classify newly generated `.cube` or `.cub` files by filename and manifest metadata.

## Common fixes

- If Multiwfn exits immediately, the input file may be unsupported or the binary path is wrong.
- If Multiwfn hangs, the recipe reached a prompt that expects a value not supplied in the `.inp` file.
- If cube files are generated but not classified, rename them or pass `--esp-cube` and `--density-cube` explicitly.
- If ESP coloring looks inverted, check whether the renderer palette maps negative values to red or blue and state the convention used.
