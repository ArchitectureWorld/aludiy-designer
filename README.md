# AluDIY Designer

面向 DIY 家居铝型材的线驱动设计工具。第一阶段以 Blender 5.2.x LTS 为体验式验收环境：用户精确绘制工程线，系统从独立型材目录生成联动三维体量和结构化项目数据。

## 当前版本

`v0.1.6-alpha`

已包含：

- 独立于 Blender 的工程数据内核；
- 五种测试型材及稳定槽位接口语义；
- JSON 型材源包到 SQLite 运行目录；
- `mm / cm / m`、安全算术和 `@长度<角度` 精确输入；
- 固定起端、固定末端、固定中心的型材改长；
- Blender 双视窗、完整视角/缩放联动、轴线/实体选择联动；
- 左侧纯工程线视窗与右侧实体视窗的逐视窗集合隔离；
- 右侧 `BOX` / 槽位语义型材细节两级显示；
- 连续画线和样例框架；
- 工程线起绿终红方向渐变及端点标记；
- Rhino 式十字光标、节点吸附、坐标、长度和角度动态反馈；
- `XY / XZ / YZ` 构造平面、首点平面偏移与 `X / Y / Z` 世界轴锁定；
- 任意高度节点的屏幕吸附、垂直立柱和顶标高连续画线；
- `Ctrl + Shift + Delete` 工程删除：线／实体同步删除、共享节点保留、孤立节点清理和撤销；
- 精确节点坐标、型材起终点与 XYZ 增量平移；
- 共享节点驱动相邻型材更新及 revision 传播；
- 选中型材临时参考尺寸与节点坐标反馈；
- 随版本更新的可视化开发进度看板；
- 项目 JSON 与基础切割清单 CSV。

未包含：连接求解、自动退让、供应商制造级精确 T 槽截面、板材、报价、下单及 AI。

说明：逐视窗集合隔离与缩放同步已实现，但仍需在目标 Blender 5.2.2 图形界面完成实际交互验收。型材细节是目录槽位语义生成的 LOD1 交互模型，并非制造级 DXF/STEP。

## 下载、安装与更新

构建后使用：

```text
dist/aludiy_designer-0.1.6.zip
```

远程仓库首次发布后，在 Blender 5.2.x LTS 的 **Preferences → Extensions → Repositories** 中添加：

```text
https://architectureworld.github.io/aludiy-designer/index.json
```

随后可直接 `Refresh Remote → Update`。从旧的本地 ZIP 安装迁移到远程版时，可能需要最后卸载一次旧版。完整步骤见 [`docs/acceptance/v0.1.6-alpha.md`](docs/acceptance/v0.1.6-alpha.md)。

## 开发

```bash
pytest -q
python tools/build_catalog.py
python tools/sync_core_into_extension.py
python tools/build_extension.py
```

核心代码位于 `src/aludiy_core/`，不得导入 `bpy`。Blender 适配层位于 `extension/aludiy_designer/`，通过稳定 ID 将工程对象映射为轴线和实体缓存。

## 目录结构

```text
src/aludiy_core/                 Blender 无关工程内核
catalog/profiles/                可版本化型材源数据
extension/aludiy_designer/       Blender 5.2 Extension
examples/                        样例工程与切割清单
docs/acceptance/                 体验式验收脚本
docs/superpowers/                设计规格与实施计划
tests/                           核心与扩展静态测试
```

## 验证状态

普通 Python 自动化测试和静态编译在构建环境执行。由于该环境没有 Blender 二进制文件，实际 Blender 5.2.2 启动验证需要在目标机器运行：

```bash
blender --background --factory-startup --python tools/blender_smoke_test.py
```
