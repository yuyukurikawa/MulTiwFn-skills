# Multiwfn Aromaticity Recipes

Use this file when a generated recipe fails or when a user requests a specific aromaticity route. Menu numbers are based on the local Multiwfn source tree checked during skill creation.

## Main Entry

Most aromaticity functions live under main function `25`:

```text
25 Electron delocalization and aromaticity analyses
```

Related helper routes:

- `15`: Fuzzy atomic space analysis for PDI, FLU, FLU-pi, PLR, multicenter DI, and ITA.
- `2`: Topology analysis for Shannon aromaticity and ring critical point properties.
- `100 -> 14`: LOLIPOP.

## Geometry Routes

Use a structure or wavefunction file with atom indices confirmed by the user.

```text
25
6
0
<ring atom indices>
q
-1
```

This computes HOMA. For Bird, use `2` instead of `0` in the HOMA/Bird submenu. For HOMAc and HOMER use:

```text
25
6a
<ring atom indices>
q
```

```text
25
6b
<ring atom indices>
q
```

## Multicenter / AV Routes

Use a wavefunction file with density and overlap information.

```text
25
1
<ring atom indices in connectivity order>
0
```

NAO multicenter route:

```text
25
-1
<ring atom indices>
0
```

AV1245/AVmin:

```text
25
2
<ring atom indices>
q
```

## NICS / ICSS Two-Stage Routes

NICS and ICSS require Gaussian NMR output for ghost atoms (`Bq`). In v1, aromatic-skill does not run Gaussian. It generates the Gaussian input, waits for the user to run it, then resumes from `.out` or `.log`.

NICS-1D generation uses:

```text
25
13
2
<ring atoms defining plane>



1
<Gaussian NMR template with [geometry]>
0
```

NICS-1D loading/export uses the same scan definition, then:

```text
2
<Gaussian NMR output>
3

0
```

NICS-2D uses `25 -> 14` and Multiwfn's 2D grid definition prompts.

ICSS uses `25 -> 3`, first generating batches such as `NICS0001.gjf`, then loading `NICS0001.out` or `.log`.

## Fuzzy Routes

Multiwfn's aromaticity menu points these methods to main function `15`; aromatic-skill generates recipes directly for that module.

PDI:

```text
15
5
<six ring atom indices>
q
0
```

FLU:

```text
15
6
<ring atom indices>
q
0
```

FLU-pi:

```text
15
7
<pi orbital indices>
<ring atom indices>
q
0
```

PLR:

```text
15
10
<six ring atom indices>
q
0
```

Multicenter DI:

```text
15
11
<ring atom indices>
q
0
```

ITA:

```text
15
12
<ring atom indices if prompted>
0
```

## LOLIPOP

LOLIPOP is under `100 -> 14`. It requires confirmed pi orbitals and ring atoms:

```text
100
14
1
<pi orbital indices>
0
<ring atom indices>
-1
```

Adjust grid spacing, integration radius, side selection, and visualization toggles before `0` when the user requests non-default settings.
