# Multiwfn Orbital Recipes

Use this reference when Multiwfn must generate molecular orbital cube files.

## Version sensitivity

Multiwfn is menu-driven and menu numbers can vary by version and build. Keep generated `.inp` files and logs so failures are reproducible. If the default recipe fails, inspect `multiwfn_orbitals.log`, update the recipe, and rerun with:

```bash
python3 scripts/mo_pipeline.py --MO HOMO,LUMO --homo 45 --input molecule.fchk --recipe fixed_recipe.inp --execute
```

## Default batch recipe

The bundled pipeline uses the commonly documented batch route:

```text
200
3
<orbital-list>
3
1
q
```

Meaning:

- `200`: Other functions, part 2.
- `3`: Generate cube file for multiple orbital wavefunctions.
- `<orbital-list>`: orbital indices such as `45,46` or `44,45,46`.
- `3`: high-quality grid.
- `1`: export selected orbitals as separate cube files.

Expected output names are usually like `orb000045.cub` and `orb000046.cub`. The exact filename width can vary, so the pipeline rescans the output directory after Multiwfn runs.

## Safe execution rules

- Always run Multiwfn in the output directory.
- Always capture stdout/stderr to a log file.
- Always use a timeout.
- Always set `Multiwfnpath` when a local `settings.ini` directory is known.
- Never overwrite the source wavefunction file.
- Treat unsuccessful cube generation as a recipe-compatibility problem, not as a failed scientific result.

## Common fixes

- If Multiwfn exits immediately, the input file may be unsupported or the binary path is wrong.
- If Multiwfn hangs, the recipe reached a prompt that expects a value not supplied in the `.inp` file.
- If cube files are generated but not classified, pass them explicitly with `--cube HOMO=orb000045.cub` or rename them.
- If orbital signs differ between runs, remember that MO phase is arbitrary; the physical orbital is unchanged.
