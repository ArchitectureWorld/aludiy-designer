"""L/T square-cut processing UI, separate from position associations."""
import bpy
from . import runtime, g_move, profile_tools
from .vendor.aludiy_core import parse_distance_mm
from .vendor.aludiy_core.joints import set_butt_joint, remove_joints, solve_cutbacks
from .vendor.aludiy_core.errors import ValidationError


def selected_pair(context):
    spec = g_move.target_spec(context)
    mids = spec.get('member_ids', ())
    active = runtime.entity_id_from_object(context.view_layer.objects.active)
    if len(mids) != 2 or spec.get('node_ids') or active not in mids:
        raise ValidationError('请只选两根相接型材；最后选中（当前）的型材作为主杆')
    return active, next(mid for mid in mids if mid != active)


def solution(context):
    p = g_move.display_project(context.scene)
    return solve_cutbacks(p, runtime.get_catalog()) if p.joints else None


class ALUDIY_OT_set_butt_joint(bpy.types.Operator):
    bl_idname = 'aludiy.set_butt_joint'
    bl_label = '设置 / 更新 L·T 直角交接'
    bl_description = '两根型材，最后选中的是主杆；自动退让支杆，L形主杆端部补齐，设计线不动'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not profile_tools._busy()
    def execute(self, context):
        try:
            host, branch = selected_pair(context)
            gap = parse_distance_mm(runtime.settings(context.scene).joint_gap_input)
            p = runtime.get_project(context.scene)
            r = set_butt_joint(p, runtime.get_catalog(), host_member_id=host,
                               branch_member_id=branch, gap_mm=gap)
            if not r.changed_count:
                runtime.set_status(context.scene, '交接参数未改变'); return {'CANCELLED'}
            g_move._commit_relations(context, p, r.project, g_move.target_spec(context))
            runtime.set_status(context.scene, f'已设置直角交接：主杆 {host} / 支杆 {branch}；只调整实体端面，未新增位置关联')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'}, str(exc)); runtime.set_status(context.scene, str(exc))
            return {'CANCELLED'}


class ALUDIY_OT_remove_joints(bpy.types.Operator):
    bl_idname = 'aludiy.remove_joints'
    bl_label = '清除所选交接（恢复未退让实体）'
    bl_description = '仅移除选中杆件相关的实体加工规则，设计线位置和原有关联保持不变'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and not profile_tools._busy()
    def execute(self, context):
        try:
            spec = g_move.target_spec(context)
            mids = spec.get('member_ids', ())
            if spec.get('endpoint'): mids = (spec['endpoint'][0],)
            p = runtime.get_project(context.scene)
            r = remove_joints(p, member_ids=mids)
            if not r.changed_count:
                runtime.set_status(context.scene, '所选杆件没有交接规则'); return {'CANCELLED'}
            g_move._commit_relations(context, p, r.project, spec)
            runtime.set_status(context.scene, f'已清除 {r.changed_count} 条交接，位置与工程关联未改动')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'}, str(exc)); runtime.set_status(context.scene, str(exc))
            return {'CANCELLED'}


def draw_panel(layout, context):
    p = g_move.display_project(context.scene)
    box = layout.box(); box.label(text='交接与端面退让 · 首版', icon='MOD_LENGTH')
    box.label(text='直角端面对接 · 设计线不移动')
    try:
        host, branch = selected_pair(context)
        box.label(text=f'主杆 {host}（当前） / 支杆 {branch}')
        enabled = True
    except ValidationError:
        box.label(text='选两根杆件，最后选中主杆')
        enabled = False
    box.prop(runtime.settings(context.scene), 'joint_gap_input', text='端面间隙 mm')
    row = box.row(); row.enabled = enabled and not profile_tools._busy()
    row.operator('aludiy.set_butt_joint', icon='MOD_LENGTH')
    row = box.row(); row.enabled = bool(p.joints) and not profile_tools._busy()
    row.operator('aludiy.remove_joints', icon='X')
    if p.joints:
        result = solve_cutbacks(p, runtime.get_catalog())
        if result.issues:
            warning = box.box(); warning.alert = True
            warning.label(text='交接待处理：全部退让暂停，禁止出料', icon='ERROR')
            for issue in result.issues[:3]:
                # Native labels do not wrap; split text conservatively in characters.
                for i in range(0, len(issue), 23): warning.label(text=issue[i:i+23])
        else:
            mids = set(profile_tools.selected_members(context))
            for j in p.joints.values():
                if j.host_member_id in mids or j.branch_member_id in mids:
                    box.label(text=f'{j.id} · {result.kinds[j.id]} · {j.host_member_id} → {j.branch_member_id}')
    box.label(text='L：主杆端补齐 / T：主杆保持完整')
    box.label(text='加工参考，未验证槽口、接头或承载')

CLASSES = (ALUDIY_OT_set_butt_joint, ALUDIY_OT_remove_joints)
