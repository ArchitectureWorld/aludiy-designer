# AluDIY Designer · 0.1.16-alpha Preview

面向DIY家居铝型材的Blender线驱动设计工具。设计线、节点、型材目录、位置关联和实体加工规则独立管理；左右线/体视窗同步。目标验收版本为Blender5.2.2 LTS。

本版：**截面槽轨控制台、明确解关联、L/T直角交接与自动退让首版**。吸附只定位，关联仍手动创建；加工规则只改变实体，不移动设计轴线。

[体验验收](docs/acceptance/v0.1.16-alpha.md) · [可视化开发进度](docs/progress/index.html) · [验证记录](docs/verification/v0.1.16.md) · [变更历史](CHANGELOG.md)

## 更新
保存工程副本，使用原更新源 Refresh Remote → AluDIY Designer → Update，无需每轮卸载重装。

```text
https://architectureworld.github.io/aludiy-designer/index.json
```

备用包：`dist/aludiy_designer-0.1.16.zip`。首次创建L/T交接规则使用schema0.4.0，**不要用0.1.15或更旧插件覆盖保存**；没有交接的旧工程不会自动升级。

## 当前能力
- 双视窗创建/复用、透视/正交/方向/平移/缩放同步；纯工程线与BOX/型材细节。
- 工程G、端点/成组移动、mm安全数值输入、轴/平面锁定、画线/杆身/槽轨吸附。
- 多选完整高亮、当前长度在侧栏顶部；截面直接点槽、定位目标与手动关联统一入口。
- 节点/杆身/槽轨显式关联，解除保留位置，取消/撤销/保存重开。
- 批量换型/截面朝向；稳定槽位语义。已有槽轨关联主杆换型需先解除，不猜接口兼容。
- 首版正交L/T平端面退让和间隙，设计/实体参考长度分离；失效加工不锁死G，但提示待处理并禁止输出加工参考清单。
- 结构化项目JSON与长度/退让参考CSV。

“停止定位”不删除关联；“解除所选”或“解除此槽关联”才移除工程约束。“清除所选交接”只移除实体加工规则。三个动作互不冒充。

## 边界
目前仍使用五种语义测试型材，不是供应商制造级DXF/STEP。尚不包含斜切拼角、连接件选配、槽轨滑移、板材、报价/下单、结构模拟或AI。参考CSV不能直接作为生产加工单。Linux自动检查不等于Windows各显卡/DPI/插件组合已验收。

## 开发与验证

```bash
pytest -q
python tools/sync_core_into_extension.py
python tools/build_extension.py
blender --command extension validate dist/aludiy_designer-0.1.16.zip
bash tools/verify_console_joints.sh /path/to/blender evidence
```

核心位于`src/aludiy_core/`且不得依赖bpy；适配层在`extension/aludiy_designer/`；`catalog/profiles/`为可版本化目录源，SQLite仅作编译运行目录。`tools/`包含真实Blender回归与覆盖更新脚本，`docs/acceptance/`保存各版本验收说明。

Preview只发布测试通道；发布配置固定已测源码SHA，不自动合并开发分支或此前堆叠PR。
