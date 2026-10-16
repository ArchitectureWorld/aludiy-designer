"""Batch section edits and read-only slot inspection for both engineering views."""
import math
import bpy
from bpy.props import EnumProperty, StringProperty
from . import runtime, g_move, scene_adapter, selection_state
from .vendor.aludiy_core.profile_editing import edit_profiles, parse_angle_deg, interface_rails
from .vendor.aludiy_core.geometry import derive_member_mesh, section_outline_uv
from .vendor.aludiy_core.errors import ValidationError

_DRAW_HANDLE = None


def selected_members(context):
    mids, _ = g_move.selection_summary(context)
    return tuple(sorted(mids))


def active_inspector_member(context):
    mid = runtime.active_member_id(context)
    if mid:
        return mid
    ep = g_move.endpoint_context(context)
    return ep[0] if ep else None


def selected_slot(scene, member_id, project):
    s = runtime.settings(scene)
    member = project.members.get(member_id)
    if (member and s.inspected_member_id == member_id
            and s.inspected_profile_id == member.profile_type_id
            and s.inspected_interface_id in runtime.get_catalog().get(member.profile_type_id).section.interfaces):
        return s.inspected_interface_id
    return None


def clear_slot(scene):
    s = runtime.settings(scene)
    s.inspected_member_id = s.inspected_profile_id = s.inspected_interface_id = ''


def edit_selection(context, *, profile_type_id=None, roll_deg=None, relative=False):
    from .operators import _commit_project_update
    ids = selected_members(context)
    original = runtime.get_project(context.scene)
    result = edit_profiles(original, ids, runtime.get_catalog(), profile_type_id=profile_type_id,
                           roll_deg=roll_deg, relative=relative)
    if not result.changed_member_ids:
        runtime.set_status(context.scene, '规格与角度未改变')
        return False
    # Preflight the new meshes before touching any scene cache.
    for mid in result.changed_member_ids:
        derive_member_mesh(result.project, mid, runtime.get_catalog(),
                           mode=runtime.settings(context.scene).solid_display_mode)
    snapshot = selection_state.capture(context)
    try:
        _commit_project_update(context, original, result.project, selected_entity_id=ids[0])
    finally:
        selection_state.restore(context, snapshot)
    if profile_type_id is not None:
        clear_slot(context.scene)
    runtime.set_status(context.scene,
        f'已更新 {len(result.changed_member_ids)} 根（含关联影响）· 槽轨附着跟随 · Ctrl+Z 撤销')
    g_move._redraw()
    return True


class ALUDIY_OT_edit_selected_profiles(bpy.types.Operator):
    bl_idname = 'aludiy.edit_selected_profiles'
    bl_label = '修改所选型材截面'
    bl_description = '批量换型或绕各杆自身轴线旋转截面；主杆轴线不动；槽轨附着端跟随旋转，不自动适配连接件'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=(('PROFILE','替换规格',''), ('ROTATE','相对旋转',''), ('SET','设置绝对角度','')), default='PROFILE')
    angle: StringProperty(default='', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and g_move._ACTIVE is None and bool(selected_members(context))

    def execute(self, context):
        s = runtime.settings(context.scene)
        try:
            if self.action == 'PROFILE':
                changed = edit_selection(context, profile_type_id=s.edit_profile_id or runtime.get_catalog().profile_ids()[0])
            else:
                angle = parse_angle_deg(self.angle or s.profile_roll_input)
                changed = edit_selection(context, roll_deg=angle, relative=self.action == 'ROTATE')
            return {'FINISHED'} if changed else {'CANCELLED'}
        except Exception as exc:
            self.report({'WARNING'}, str(exc))
            runtime.set_status(context.scene, f'截面修改未提交：{exc}')
            return {'CANCELLED'}


class ALUDIY_OT_inspect_profile_slot(bpy.types.Operator):
    bl_idname = 'aludiy.inspect_profile_slot'
    bl_label = '检查槽位'
    bl_description = '只高亮活动杆件的语义槽轨；不吸附、不建立关联'
    interface_id: StringProperty(default='', options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and g_move._ACTIVE is None and bool(active_inspector_member(context))

    def execute(self, context):
        mid = active_inspector_member(context)
        p = runtime.get_project(context.scene)
        if mid not in p.members:
            return {'CANCELLED'}
        profile = runtime.get_catalog().get(p.members[mid].profile_type_id)
        if self.interface_id not in profile.section.interfaces:
            self.report({'WARNING'}, '当前型材不存在该槽位；请重新选择')
            return {'CANCELLED'}
        s = runtime.settings(context.scene)
        s.inspected_member_id, s.inspected_profile_id = mid, profile.profile_type_id
        s.inspected_interface_id = self.interface_id
        s.show_section_inspector = True
        runtime.set_status(context.scene, f'{mid} · {self.interface_id} · 仅检查，不建立关联')
        g_move._redraw()
        return {'FINISHED'}


def draw_panel(layout, context):
    s = runtime.settings(context.scene)
    box = layout.box()
    box.label(text='型材规格与截面朝向', icon='CUBE')
    ids = selected_members(context)
    box.label(text=f'作用于 {len(ids)} 根所选型材 · 轴线保持不动')
    box.prop(s, 'edit_profile_id')
    row = box.row(); row.enabled = bool(ids) and g_move._ACTIVE is None
    row.operator('aludiy.edit_selected_profiles', text='替换所选型材规格', icon='FILE_REFRESH').action = 'PROFILE'
    row = box.row(align=True); row.enabled = bool(ids) and g_move._ACTIVE is None
    for angle, label in [('-90','截面 −90°'), ('90','截面 +90°')]:
        op = row.operator('aludiy.edit_selected_profiles', text=label)
        op.action = 'ROTATE'; op.angle = angle
    row = box.row(align=True)
    row.prop(s, 'profile_roll_input', text='角度 °')
    sub = row.row(align=True);sub.enabled = bool(ids) and g_move._ACTIVE is None
    op = sub.operator('aludiy.edit_selected_profiles', text='设置'); op.action='SET';op.angle=''
    mid = active_inspector_member(context)
    project = g_move.display_project(context.scene)
    if mid and mid in project.members:
        m = project.members[mid]; profile = runtime.get_catalog().get(m.profile_type_id)
        box.label(text=f'当前 {mid} · {profile.display_name}')
        rolls = {round(project.members[i].roll_deg % 360, 8) for i in ids if i in project.members}
        box.label(text=f'所选角度：{next(iter(rolls)):g}°' if len(rolls)==1 else f'当前角度 {m.roll_deg % 360:g}° · 多选角度可不同')
        box.prop(s, 'show_section_inspector')
        active = selected_slot(context.scene, mid, project)
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, even_rows=True, align=True)
        for slot in sorted(profile.section.interfaces.values(),key=lambda x:x.id):
            face = slot.host_face_id.replace('FACE_P','+').replace('FACE_N','−')
            op = grid.operator('aludiy.inspect_profile_slot', text=f'{face} · 槽 {slot.lane_index+1}/{slot.lane_count}', depress=slot.id==active)
            op.interface_id=slot.id
        row=box.row();row.enabled=bool(active)
        row.operator('aludiy.set_slot_target',text='设为槽轨定位目标',icon='SNAP_EDGE')
    else:
        box.prop(s, 'show_section_inspector')
        box.label(text='选择一根型材查看截面与槽 ID')
    box.label(text='测试槽轨；吸附后仍需手动关联',icon='INFO')
    box.label(text='带槽轨附着的主杆换型需先解除关联')
    from . import slot_tools
    slot_tools.draw_panel(layout,context)


def _draw_inspector():
    c = bpy.context
    if not (c.area and c.area.type=='VIEW_3D' and c.region and c.region.type=='WINDOW'
            and c.region_data and c.workspace.name==runtime.WORKSPACE_NAME):
        return
    s = runtime.settings(c.scene)
    if not s.show_section_inspector or not s.project_json:
        return
    mid = active_inspector_member(c)
    if not mid:
        return
    from . import viewport_overlay as ov
    import gpu
    try:
        p=g_move.display_project(c.scene)
        if mid not in p.members:return
        member=p.members[mid];profile=runtime.get_catalog().get(member.profile_type_id)
        section=profile.section;angle=math.radians(member.roll_deg)
        cs,sn=math.cos(angle),math.sin(angle)
        def rotate(uv):return (cs*uv[0]-sn*uv[1],sn*uv[0]+cs*uv[1])
        outline=tuple(rotate(uv) for uv in section_outline_uv(section,detailed=True))
        # Keep the inset left of the N panel, even when region overlap is enabled.
        sidebar = next((r for r in c.area.regions if r.type=='UI'),None)
        visible_right=c.region.width
        if c.space_data.show_region_ui and sidebar and sidebar.width>1:
            visible_right=min(visible_right,sidebar.x-c.region.x)
        available=visible_right-20-(60 if c.space_data.show_region_toolbar else 0)
        if available<175 or c.region.height<340:return
        w=min(235,available);h=268;x=visible_right-w-12;y=c.region.height-h-18
        gpu.state.blend_set('ALPHA')
        ov._filled_rect(x,y,w,h,(.035,.045,.055,.94))
        ov._text(x+10,y+h-22,f'{mid} · 截面 / 测试目录',size=12)
        ov._text(x+10,y+h-42,f'U {section.width_mm:g} × V {section.height_mm:g} mm · {member.roll_deg%360:g}°',size=12)
        ov._text(x+10,y+h-60,'终端看向起端 · 相对 0° 基准',size=10)
        span=max(max(abs(a) for a,b in outline),max(abs(b) for a,b in outline),1)
        scale=min((w-78)/2,55)/span;cx=x+w*.5;cy=y+124
        def local(uv):
            u,v=rotate(uv);return (cx+scale*u,cy+scale*v)
        ring=[(cx+scale*u,cy+scale*v) for u,v in outline]
        points=[]
        for i in range(len(ring)):points.extend([ring[i],ring[(i+1)%len(ring)]])
        ov._polyline(points,color=(.85,.93,1,1),width=1.4)
        sid=selected_slot(c.scene,mid,p)
        for slot in section.interfaces.values():
            pt=local(slot.center_uv_mm);active=slot.id==sid
            color=(1,.72,.1,1) if active else (.2,.78,1,1)
            g_move._disc(pt,4.3 if active else 2.5,color)
            pos=tuple(slot.center_uv_mm[i]+slot.outward_normal_uv[i]*7/scale for i in range(2))
            tx,ty=local(pos);face=slot.host_face_id.replace('FACE_P','+').replace('FACE_N','−')
            label=f'{face}.{slot.lane_index+1}'
            u,v=rotate(slot.outward_normal_uv)
            if u<-.1:tx-=30
            if v<-.1:ty-=10
            ov._text(tx,ty,label,size=9,color=color)
        ov._text(x+10,y+38,'检查只读；设为目标可定位',size=10)
        ov._text(x+10,y+22,sid or '点击右侧槽位按钮查看',size=11,color=(1,.75,.25,1) if sid else ov.TEXT_COLOR)
        ov._text(x+10,y+7,'槽形为示意，非制造级截面',size=9)
        if sid:
            rail=next(r for r in interface_rails(p,mid,runtime.get_catalog()) if r.interface_id==sid)
            a,b=ov._project(rail.start_mm),ov._project(rail.end_mm)
            if a is not None and b is not None:
                ov._polyline([tuple(a),tuple(b)],color=(1,.67,.1,1),width=3)
                center=(a+b)*.5
                ov.draw_snap_marker(tuple(center),color=(1,.72,.1,1))
    except Exception as exc:
        print(f'AluDIY section inspector: {exc}')
    finally:
        gpu.state.blend_set('NONE')


def register_services():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is None:
        _DRAW_HANDLE=bpy.types.SpaceView3D.draw_handler_add(_draw_inspector,(), 'WINDOW','POST_PIXEL')


def unregister_services():
    global _DRAW_HANDLE
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE,'WINDOW');_DRAW_HANDLE=None


CLASSES=(ALUDIY_OT_edit_selected_profiles,ALUDIY_OT_inspect_profile_slot)
