# ESP Visualization

Use this reference when rendering ESP surface figures.

## Renderer choice

Prefer VMD/Tachyon for unattended macOS rendering when available. Use ChimeraX when VMD is unavailable or the user specifically requests ChimeraX/offscreen output.

## Visual defaults

- Canvas: 2400 x 1800 px.
- Background: white by default.
- Projection: orthographic.
- Surface: electron density isosurface, default isovalue `0.001` a.u.
- ESP range: default `-0.05` to `0.05` a.u.; use a wider range for ions or very polar molecules.
- Palette: negative ESP blue, neutral white, positive ESP red unless the user specifies another convention.
- Style: clean atoms/bonds, no axes, soft lighting, ambient occlusion or shadows when supported.

## ChimeraX notes

The pipeline writes `render_chimerax.cxc`. It opens the structure or density cube, opens the ESP cube, styles the density volume surface, samples ESP values onto the surface when supported, and saves a PNG with supersampling.

Run manually if needed:

```bash
ChimeraX --offscreen --script render_chimerax.cxc
```

## VMD notes

The pipeline writes `render_vmd.tcl`. It opens structure/cube files, creates a density isosurface representation, colors it by the ESP volume, applies a diverging color scale, enables orthographic projection and ambient occlusion when supported, writes a Tachyon scene when external Tachyon is available, renders at the requested resolution, and converts TGA to PNG when possible.

Run manually if needed:

```bash
vmd -dispdev text -e render_vmd.tcl
```

## QA

An image is acceptable only if it exists and is nonempty. PNG outputs should also have a plausible PNG header. If the script reports a rendering command but no image, return the script and logs instead of claiming success.
