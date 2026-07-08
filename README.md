<h1 align="center">
  <img src="assets/multiwfn-title.svg" alt="MulTiwFn" width="520">
</h1>

<p align="center">
  Multiwfn 驱动的计算化学波函数分析与可视化 Codex Skill 集合
</p>

<p align="center">
  <a href="#安装">安装</a> ·
  <a href="#技能索引">技能索引</a> ·
  <a href="#快速使用">快速使用</a> ·
  <a href="#目录结构">目录结构</a>
</p>

<p align="center">
  <img alt="Codex Skill" src="https://img.shields.io/badge/Codex-Skill-111827">
  <img alt="Multiwfn" src="https://img.shields.io/badge/Multiwfn-required-5BCEFA">
  <img alt="VMD" src="https://img.shields.io/badge/VMD-rendering-F5A9B8">
  <img alt="ChimeraX" src="https://img.shields.io/badge/ChimeraX-fallback-FFFFFF">
</p>

MulTiwFn 是一个面向计算化学工作流的 Codex skill 仓库。它让 Codex 可以从本机自动发现波函数文件、结构文件和可视化程序，调用 Multiwfn 生成 cube 数据，再用 VMD/Tachyon 或 ChimeraX 渲染适合论文展示的分子图像。

## 安装

### Codex 推荐安装方式

推荐把完整 skill 文件夹复制到 Codex 的 skills 目录。不要只复制 `SKILL.md`，因为每个 skill 还依赖 `scripts/`、`references/` 和 `agents/`。

```bash
git clone https://github.com/yuyukurikawa/MulTiwFn-skill.git
cd MulTiwFn-skill

mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R esp-surface-skill "${CODEX_HOME:-$HOME/.codex}/skills/"
cp -R orb-visualize-skill "${CODEX_HOME:-$HOME/.codex}/skills/"
```

安装后重启 Codex 会话，确认能看到两个 skill：

```bash
ls "${CODEX_HOME:-$HOME/.codex}/skills"
```

注意：当前仓库文件夹名为了发布更简洁，分别是 `esp-surface-skill` 和 `orb-visualize-skill`；Codex 调用时读取的是 `SKILL.md` 中的内部名称：

```text
$esp-surface-analysis
$molecular-orbital-visualization
```

### Multiwfn 安装方式

MulTiwFn 需要本机已安装 Multiwfn。推荐从 Multiwfn 官方下载页获取与你的系统匹配的版本：

- Multiwfn: <https://sobereva.com/multiwfn/download.html>

如果 `Multiwfn` 不在 `PATH` 中，运行 pipeline 时可以显式指定：

```bash
python3 orb-visualize-skill/scripts/mo_pipeline.py \
  --MO HOMO,LUMO \
  --homo 21 \
  --input benzene.molden.input \
  --multiwfn-bin /path/to/Multiwfn \
  --execute
```

### VMD 安装方式

VMD 是当前默认的渲染后端，用于调用 Tachyon 输出白底、正交投影、带光照的 MO/ESP 图片。

1. 从 VMD 官方下载页选择适合系统的版本：<https://www.ks.uiuc.edu/Development/Download/download.cgi?PackageName=VMD>
2. macOS 用户通常把 `.app` 放入 `/Applications`。
3. 检查 VMD 和 Tachyon 是否能被发现：

```bash
find /Applications -path '*VMD*.app/Contents/vmd*/vmd_*' -o -path '*VMD*.app/Contents/vmd*/tachyon_*'
```

如果自动发现失败，可以手动指定 VMD：

```bash
python3 orb-visualize-skill/scripts/mo_pipeline.py \
  --MO HOMO,LUMO \
  --homo 21 \
  --input benzene.molden.input \
  --renderer vmd \
  --vmd-bin /path/to/vmd \
  --execute
```

### ChimeraX 安装方式

ChimeraX 作为备用渲染后端，适合 VMD 不可用或需要后续扩展结构展示样式时使用。

1. 从 UCSF ChimeraX 官方下载页安装：<https://www.cgl.ucsf.edu/chimerax/download.html>
2. macOS 用户通常把 `.app` 放入 `/Applications`。
3. 检查可执行文件是否存在：

```bash
find /Applications -path '*ChimeraX*.app/Contents/MacOS/ChimeraX'
```

如果自动发现失败，可以手动指定 ChimeraX：

```bash
python3 esp-surface-skill/scripts/esp_pipeline.py \
  --ESP \
  --input benzene.molden.input \
  --renderer chimerax \
  --chimerax-bin /path/to/ChimeraX \
  --execute
```

## 技能索引

| Skill | 触发方式 | 适合任务 | 主要输出 |
| --- | --- | --- | --- |
| `input-skill` | SMILES、Gaussian input、ORCA input、`--smiles` | 从 SMILES 生成 3D 结构，询问缺失参数，并基于精选 benchmark 文献库推荐方法/基组，按需输出 Gaussian、ORCA 或二者的输入文件 | `structure.xyz`、选中的 `<name>.gjf`/`<name>.inp`、`recommendation.md`、`manifest.json` |
| `esp-surface-analysis` | `--ESP`、ESP、MEP、静电势表面 | 从 `.fchk`、`.molden`、`.wfn`、`.wfx`、cube 等文件生成 ESP 着色分子表面 | `density.cub`、`totesp.cub`、渲染脚本、`esp_vmd.png` 或 ChimeraX PNG、`manifest.json` |
| `molecular-orbital-visualization` | `--MO`、HOMO、LUMO、分子轨道、MO cube | 生成指定轨道的 cube，并交付每个轨道的正视图和侧视图 | `<orbital>.cub`、`<orbital>_front.png`、`<orbital>_side.png`、渲染脚本、`summary.md`、`manifest.json` |

## 快速使用

### 在 Codex 中调用 MO skill

```text
Use $molecular-orbital-visualization --MO HOMO,LUMO --homo 21，input file is benzene.molden.input
```

### 直接运行 MO pipeline

```bash
python3 orb-visualize-skill/scripts/mo_pipeline.py \
  --MO HOMO,LUMO \
  --homo 21 \
  --input benzene.molden.input \
  --execute
```

常用参数：

- `--MO HOMO,LUMO,HOMO-1,LUMO+1`：选择要渲染的轨道。
- `--homo 21`：使用 HOMO/LUMO 相对表达式时必须提供 HOMO 轨道编号。
- `--structure benzene.xyz`：指定结构文件，帮助渲染键线。
- `--front-axis z --side-axis x`：手动覆盖正视图和侧视图方向。
- `--isovalue 0.03`：设置轨道等值面。

### 在 Codex 中调用 ESP skill

```text
Use $esp-surface-analysis --ESP，input file is benzene.molden.input
```

### 直接运行 ESP pipeline

```bash
python3 esp-surface-skill/scripts/esp_pipeline.py \
  --ESP \
  --input benzene.molden.input \
  --execute
```

常用参数：

- `--density-isovalue 0.001`：设置电子密度等值面。
- `--esp-range -0.05,0.05`：设置 ESP 颜色范围，单位为 a.u.。
- `--renderer vmd`：强制使用 VMD/Tachyon。
- `--renderer chimerax`：强制使用 ChimeraX。

## 目录结构

```text
.
├── README.md
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

## 输出与复现

每次运行 pipeline 都会写出 `manifest.json`，记录自动发现到的文件、程序路径、实际命令、warning 和输出文件。渲染失败时，优先检查同一输出目录下的 Multiwfn recipe、VMD/ChimeraX 脚本和 log。

建议不要把大型计算产物提交到 GitHub。仓库的 `.gitignore` 已默认忽略常见 ORCA 输出、cube 文件和本地测试目录。

## 注意事项

- `input-skill` 的 SMILES 到 3D 流程只生成单个 RDKit 构象。
- `input-skill` 不会推断电荷和自旋多重度；请在生成前确认 `charge` 和 `multiplicity`。
- 方法/基组推荐来自部分benchmark文献库，复杂开壳层、过渡金属、多参考体系仍需人工复核。
- MO 相位本身是任意的，同一轨道的正负颜色互换不改变物理含义。
- 使用 `HOMO`、`LUMO`、`HOMO-1`、`LUMO+1` 时，v1 不会自动猜 HOMO 编号，必须由用户提供 `--homo N`。
- Multiwfn 菜单 recipe 可能随版本变化；如果真实体系失败，应保留 log 和 recipe，用当前 Multiwfn 版本校准后再更新 skill。
- ChimeraX 的 offscreen 渲染在不同 macOS/OpenGL 环境下可能表现不同；无人值守生成图像时优先使用 VMD/Tachyon。
- 如果 Multiwfn 被用于你的研究，正文中至少必须引用以下论文：
• Tian Lu, Feiwu Chen, Multiwfn: A Multifunctional Wavefunction Analyzer, J. Comput. Chem. 33, 580-592 (2012) DOI: 10.1002/jcc.22885
• Tian Lu, A comprehensive electron wavefunction analysis toolbox for chemists, Multiwfn, J. Chem. Phys., 161, 082503 (2024) DOI: 10.1063/5.0216272
