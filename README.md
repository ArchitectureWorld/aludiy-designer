# AluDIY Designer

[![CI](https://github.com/ArchitectureWorld/aludiy-designer/actions/workflows/ci.yml/badge.svg)](https://github.com/ArchitectureWorld/aludiy-designer/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)

面向 DIY 家居铝型材的线驱动设计工具。第一阶段以 Blender 5.2.x LTS 为体验式验收环境：用户绘制精确工程线，系统从独立型材目录生成联动三维体量和结构化项目数据。

## 当前版本

`v0.1.5-alpha`

当前基础能力包括：

- 独立于 Blender 的工程数据内核；
- 五种测试型材及稳定槽位接口语义；
- JSON 型材源包编译为 SQLite 运行目录；
- `mm / cm / m`、安全算术和 `@长度<角度` 精确输入；
- Blender 双视窗、旋转／缩放联动、左侧工程线与右侧实体联动；
- 右侧 `BOX` / 槽位语义细节两级显示；
- Rhino 式连续画线、十字光标、节点吸附、坐标、长度与角度反馈；
- `XY / XZ / YZ` 构造平面及 `X / Y / Z` 世界轴锁定；
- 垂直立柱、高位节点吸附和顶标高连续画线；
- `Ctrl + Shift + Delete` 工程删除；
- 项目 JSON 与基础长度 CSV；
- 随版本更新的可视化开发进度看板。

尚未包含：节点求解、自动退让、制造级精确 T 槽截面、连接件、板材、正式 BOM、报价、下单及 AI。

## 安装和更新

### 当前 v0.1.5-alpha

当前版本仍可通过 Blender 的 **Preferences → Extensions → Install from Disk** 安装本地 ZIP。

### 从 v0.1.6-alpha 开始

项目将使用 Blender 远程扩展仓库：

```text
https://architectureworld.github.io/aludiy-designer/index.json
```

仓库启用后，只需在 Blender 中执行：

```text
Preferences → Extensions → Refresh Remote → Update
```

从本地 ZIP 迁移到远程仓库版本时，可能需要最后卸载一次本地安装版；远程版本保持固定扩展 ID `aludiy_designer`，后续原位更新。

开发进度看板的稳定地址计划为：

```text
https://architectureworld.github.io/aludiy-designer/progress/
```

GitHub Pages 首次发布前，仓库管理员需要在 **Settings → Pages → Source** 中选择 **GitHub Actions**。

## 开发

```bash
python -m pip install pytest
pytest -q
python tools/build_catalog.py
python tools/sync_core_into_extension.py
python tools/build_extension.py
```

核心代码位于 `src/aludiy_core/`，不得导入 `bpy`。Blender 适配层位于 `extension/aludiy_designer/`，通过稳定 ID 将工程对象映射为轴线和实体缓存。

### 确定性构建

```bash
PACKAGE="$(python tools/release_meta.py package-name)"
python tools/build_extension.py
cp "dist/${PACKAGE}" /tmp/first.zip
python tools/build_extension.py
cmp /tmp/first.zip "dist/${PACKAGE}"
```

### Blender 图形环境验收

```bash
blender --background --factory-startup --python tools/blender_smoke_test.py
```

普通 Python 测试不能替代真实 Blender 5.2.x 的视口、快捷键和 GPU 叠加层验收。

## 发布流程

1. 更新 `extension/aludiy_designer/blender_manifest.toml` 中的版本；
2. 更新 `CHANGELOG.md` 和对应验收文档／进度看板；
3. 确保 `main` 分支 CI 通过；
4. 创建标签，例如 `v0.1.6-alpha`；
5. GitHub Actions 自动执行测试、打包、GitHub Release 和 GitHub Pages 发布；
6. Blender 官方 `extension server-generate` 命令生成远程仓库 `index.json`。

标签版本必须与扩展 Manifest 版本一致。

## 目录结构

```text
src/aludiy_core/                 Blender 无关工程内核
catalog/profiles/                可版本化型材源数据
extension/aludiy_designer/       Blender 5.2 Extension
examples/                        样例工程与切割清单
docs/acceptance/                 体验式验收脚本
docs/progress/                   可视化开发进度
docs/superpowers/                设计规格与实施计划
tests/                           核心与扩展静态测试
tools/                           目录、插件、站点和发布工具
.github/workflows/               CI 与发布自动化
```

## 数据与许可边界

代码按 [GNU GPL-3.0-or-later](LICENSE) 发布。公开仓库不得提交：

- 未取得再分发许可的供应商 DXF／STEP；
- 供应商内部价格、采购合同或访问凭据；
- 用户订单、个人资料或其他私有项目数据。

当前测试截面是平台自建的语义验证数据，不代表供应商制造级产品。
