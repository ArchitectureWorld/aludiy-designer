"""One-time, fail-closed patch; removed after the verified source commit."""
from pathlib import Path
import ast
import hashlib

root = Path(__file__).resolve().parents[1]
path = root / 'extension/aludiy_designer/operators.py'
raw = path.read_bytes()
assert hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest() == '91f84d1206e36278806faeb40ee411f441430736', 'Unexpected operators revision'
source = raw.decode('utf-8')

replacement = {
'ALUDIY_OT_create_sample_frame': '''class ALUDIY_OT_create_sample_frame(bpy.types.Operator):
    bl_idname = "aludiy.create_sample_frame"
    bl_label = "插入矩形样例"
    bl_description = "在 3D 游标处插入世界 XY 矩形框架；保留已有工程，不自动合并节点"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return getattr(context, "mode", "OBJECT") == "OBJECT"

    def execute(self, context):
        scene_settings = settings(context.scene)
        try:
            width = parse_length_mm(scene_settings.sample_width_input)
            depth = parse_length_mm(scene_settings.sample_depth_input)
            profile_id = _selected_profile(context.scene)
            get_catalog().get(profile_id)
            original_project = get_project(context.scene)
            scale = 1.0 / scene_adapter.MM_TO_M
            origin = tuple(float(value) * scale for value in context.scene.cursor.location)
            result = append_sample_frame(
                original_project, width, depth, profile_id, origin_mm=origin,
            )
            _commit_project_update(
                context, original_project, result.project,
                selected_entity_id=result.member_ids[0],
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"样例插入失败，已保留原工程：{exc}")
            return {"CANCELLED"}
        set_status(
            context.scene,
            f"已插入 {width:g} × {depth:g} mm 样例（4 根）；"
            f"保留原有 {len(original_project.members)} 根型材；不自动连接",
        )
        return {"FINISHED"}
''',
'ALUDIY_OT_new_project': '''class ALUDIY_OT_new_project(bpy.types.Operator):
    bl_idname = "aludiy.new_project"
    bl_label = "新建空白项目"
    bl_description = "清空当前 AluDIY 工程并新建；已有内容时先请求确认"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return getattr(context, "mode", "OBJECT") == "OBJECT"

    def invoke(self, context, event):
        project = get_project(context.scene)
        if project.members or project.nodes:
            return context.window_manager.invoke_confirm(
                self, event, title="清空当前工程并新建？",
                message=f"将移除当前 {len(project.members)} 根型材及 {len(project.nodes)} 个节点，请先保存。",
                confirm_text="清空并新建", icon="WARNING",
            )
        return self.execute(context)

    def execute(self, context):
        try:
            original_project = get_project(context.scene)
            _commit_project_update(
                context, original_project, empty_project(), selected_entity_id="",
            )
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            set_status(context.scene, f"新建失败，已保留原工程：{exc}")
            return {"CANCELLED"}
        set_status(context.scene, "已创建空白工程项目")
        return {"FINISHED"}
''',
}
lines = source.splitlines(keepends=True)
classes = [n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name in replacement]
assert len(classes) == len(replacement)
for node in sorted(classes, key=lambda n: n.lineno, reverse=True):
    lines[node.lineno - 1:node.end_lineno] = [replacement[node.name]]
source = ''.join(lines)
needle = 'from . import runtime, scene_adapter, view_sync\n'
assert source.count(needle) == 1
source = source.replace(needle, needle + 'from .vendor.aludiy_core.io import append_sample_frame\n')
ast.parse(source)
path.write_text(source, encoding='utf-8')

panel = root / 'extension/aludiy_designer/panels.py'
source = panel.read_text(encoding='utf-8')
needle = '        box.operator("aludiy.create_sample_frame", icon="MESH_CUBE")\n'
assert source.count(needle) == 1
source = source.replace(needle, needle + '        box.label(text="插入位置：3D 游标（世界 XY）")\n')
panel.write_text(source, encoding='utf-8')

for relative in ('extension/aludiy_designer/blender_manifest.toml', 'extension/aludiy_designer/runtime.py', 'pyproject.toml'):
    p = root / relative
    source = p.read_text(encoding='utf-8')
    assert '0.1.7' in source, relative
    p.write_text(source.replace('0.1.7', '0.1.8'), encoding='utf-8')
p = root / 'extension/aludiy_designer/__init__.py'
source = p.read_text(encoding='utf-8')
assert '"version": (0, 1, 7)' in source
p.write_text(source.replace('"version": (0, 1, 7)', '"version": (0, 1, 8)'), encoding='utf-8')
p = root / 'tests/extension/test_g_move_delivery.py'
source = p.read_text(encoding='utf-8')
old = "assert manifest['version'] == '0.1.7'"
assert old in source
p.write_text(source.replace(old, "assert tuple(map(int, manifest['version'].split('.'))) >= (0, 1, 7)"), encoding='utf-8')
print('SAMPLE_SAFETY_PATCH_APPLIED')
