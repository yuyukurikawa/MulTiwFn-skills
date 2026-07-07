# Orbital Visualization

Use this reference when rendering molecular orbital figures.

## Renderer choice

Prefer VMD/Tachyon when available because it is commonly used for Multiwfn orbital cube rendering and supports clean isosurface styling. Use ChimeraX when VMD is unavailable or the user requests ChimeraX/offscreen PNG output.

## Visual defaults

- Canvas: 2400 x 1800 px.
- Background: white.
- Projection: orthographic.
- Isovalue: `0.03` a.u.
- Phase colors: positive orange, negative blue.
- Surface material: ambient-occlusion capable material when supported.
- Atoms: compact CPK/ball style, element colors.
- Axes: hidden.
- Required views: `front` and `side`.

## VMD notes

The pipeline writes `render_<orbital>_<view>.tcl`. It opens the structure or cube file, adds positive and negative orbital isosurfaces, applies a view matrix, writes a Tachyon scene, runs the local Tachyon executable at the requested resolution when available, and converts the intermediate TGA to PNG when a local converter is available. If external Tachyon is unavailable, it falls back to `TachyonInternal`.

Run manually if needed:

```bash
vmd -dispdev text -e render_HOMO_front.tcl
```

## ChimeraX notes

The pipeline writes `render_<orbital>_<view>.cxc`. It opens the structure/cube, draws positive and negative volume levels, applies an orthographic camera, and saves PNG with supersampling.

Run manually if needed:

```bash
ChimeraX --offscreen --script render_HOMO_front.cxc
```

## QA

An image is acceptable only if it exists and is nonempty. PNG outputs should also have a plausible PNG header. If the script reports a rendering command but no image, return the script and logs instead of claiming success.
