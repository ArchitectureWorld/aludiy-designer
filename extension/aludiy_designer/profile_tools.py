"""Batch section edits and directly selectable slot inspection in both views."""
import math
from types import SimpleNamespace
import bpy
from bpy.props import EnumProperty, StringProperty
from . import runtime, g_move, scene_adapter, selection_state
from .vendor.aludiy_core.profile_editing import edit_profiles, parse_angle_deg, interface_rails
from .vendor.aludiy_core.geometry import derive_member_mesh, section_outline_uv
from .vendor.aludiy_core.errors import ValidationError

_DRAW_HANDLE = None
_CURSOR_BY_WINDOW = {}
_PENDING_ACTIONS = {}


def selected_members(context):
    mids, _ = g_move.selection_summary(context)
    return tuple(sorted(mids))


def active_inspector_member(context):
    # Local Collections can hide the selected node/alias in the other viewport.
    # Use the same view-layer selection as engineering G, not area visibility.
    mids, _ = g_move.selection_summary(context)
    active = runtime.entity_id_from_object(context.view_layer.objects.active)
    if active in mids:
        return active
    ep = g_move.endpoint_context(context)
    return ep[0] if ep else (sorted(mids)[0] if mids else None)


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
        from . import operators
        return (context.mode == 'OBJECT' and g_move._ACTIVE is None
                and operators._ACTIVE_DRAW is None and bool(active_inspector_member(context)))

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
        box.label(text='槽轨操作统一在截面小窗中')
    else:
        box.prop(s, 'show_section_inspector')
        box.label(text='选择一根型材查看截面与槽 ID')



def inspector_layout(context, project=None):
    """Return the exact visible geometry, or None (also no hit area)."""
    c = context
    if not (c.area and c.area.type == 'VIEW_3D' and c.region
            and c.region.type == 'WINDOW' and c.workspace
            and c.workspace.name == runtime.WORKSPACE_NAME and c.mode == 'OBJECT'):
        return None
    settings = runtime.settings(c.scene)
    if not settings.show_section_inspector or not settings.project_json:
        return None
    mid = active_inspector_member(c)
    project = project if project is not None else g_move.display_project(c.scene)
    if mid not in project.members:
        return None
    profile = runtime.get_catalog().get(project.members[mid].profile_type_id)
    from .vendor.aludiy_core.section_picker import section_layout
    right = c.region.width
    sidebar = next((r for r in c.area.regions if r.type == 'UI'), None)
    if c.space_data.show_region_ui and sidebar and sidebar.width > 1:
        right = min(right, sidebar.x-c.region.x)
    toolbar = next((r for r in c.area.regions if r.type == 'TOOLS'), None)
    left = max(0,toolbar.x+toolbar.width-c.region.x) if toolbar and c.space_data.show_region_toolbar else 0
    geometry = section_layout(profile.section, project.members[mid].roll_deg,
        region_width=c.region.width, region_height=c.region.height,
        visible_right=right, toolbar_width=left, ui_scale=c.preferences.system.ui_scale or c.preferences.view.ui_scale)
    return (SimpleNamespace(member_id=mid, project=project, profile=profile, layout=geometry)
            if geometry is not None else None)


def _busy():
    from . import operators
    return g_move._ACTIVE is not None or operators._ACTIVE_DRAW is not None


def record_pointer(context, event):
    if context.window:
        _CURSOR_BY_WINDOW[context.window.as_pointer()] = (event.mouse_x, event.mouse_y)


def hovered_slot(context, view):
    if not view or _busy() or not context.window:
        return None
    point = _CURSOR_BY_WINDOW.get(context.window.as_pointer())
    if point is None:
        return None
    hit = view.layout.hit((point[0]-context.region.x,point[1]-context.region.y))
    return hit[1] if hit and hit[0] == 'SLOT' else None


def inset_event_hit(context, event):
    """Modal operators retain their invocation area; locate the actual mouse area."""
    if not context.window or context.workspace.name != runtime.WORKSPACE_NAME:
        return None
    record_pointer(context, event)
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        region = g_move._window_region(area)
        if not region or not (region.x <= event.mouse_x < region.x+region.width
                              and region.y <= event.mouse_y < region.y+region.height):
            continue
        with context.temp_override(window=context.window,area=area,region=region):
            view = inspector_layout(bpy.context)
        if view:
            hit = view.layout.hit((event.mouse_x-region.x,event.mouse_y-region.y))
            if hit:
                return area, region, view, hit
    return None


def handle_inspector_click(context, event):
    target = inset_event_hit(context, event)
    if not target:
        return False
    area, region, view, (action, sid) = target
    # Consume empty/disabled parts too: never select the model behind the card.
    if not _busy():
        with context.temp_override(window=context.window,area=area,region=region):
            if action == 'SLOT':
                bpy.ops.aludiy.inspect_profile_slot(interface_id=sid)
            elif action == 'PIN' and bpy.ops.aludiy.set_slot_target.poll():
                bpy.ops.aludiy.set_slot_target()
            elif action == 'CLEAR' and runtime.settings(context.scene).slot_target_member_id:
                bpy.ops.aludiy.clear_slot_target()
            elif action in {'CREATE','UNLINK_SELECTED','UNLINK_SLOT'}:
                try:
                    queue_data_action(bpy.context, action, view)
                except (ValidationError, RuntimeError, ReferenceError) as exc:
                    runtime.set_status(context.scene, f'关联操作未执行：{exc}')
    g_move._redraw()
    return True


def queue_data_action(context, action, view):
    """Run after the read-only picker returns, as a top-level undoable operator.

    Blender suppresses undo for nested operator calls. One checked next-event
    callback preserves a single normal Undo step, without manual undo_push or
    duplicate competing LEFTMOUSE keymaps. Stale selection/data cancels safely.
    """
    import json
    window_id=context.window.as_pointer();area_id=context.area.as_pointer()
    if window_id in _PENDING_ACTIONS:return
    raw=runtime.settings(context.scene).project_json
    spec=json.dumps(g_move.target_spec(context),sort_keys=True)
    target=(runtime.settings(context.scene).slot_target_member_id,
            runtime.settings(context.scene).slot_target_interface_id)
    sid=selected_slot(context.scene,view.member_id,view.project);mid=view.member_id
    scene_id=context.scene.as_pointer()
    def dispatch():
        _PENDING_ACTIONS.pop(window_id,None)
        try:
            window=next((w for w in bpy.context.window_manager.windows if w.as_pointer()==window_id),None)
            if window is None or window.scene.as_pointer()!=scene_id:return None
            area=next((a for a in window.screen.areas if a.as_pointer()==area_id and a.type=='VIEW_3D'),None)
            if area is None:return None
            region=g_move._window_region(area)
            if region is None:return None
            with bpy.context.temp_override(window=window,area=area,region=region):
                c=bpy.context;s=runtime.settings(c.scene)
                if (_busy() or s.project_json!=raw or json.dumps(g_move.target_spec(c),sort_keys=True)!=spec
                        or (s.slot_target_member_id,s.slot_target_interface_id)!=target):
                    runtime.set_status(c.scene,'操作对象已变化，关联操作未执行，请重新点击')
                    return None
                if action=='CREATE' and bpy.ops.aludiy.create_associations.poll():
                    bpy.ops.aludiy.create_associations('EXEC_DEFAULT',True)
                elif action=='UNLINK_SELECTED' and bpy.ops.aludiy.remove_associations.poll():
                    bpy.ops.aludiy.remove_associations('EXEC_DEFAULT',True)
                elif action=='UNLINK_SLOT' and sid:
                    bpy.ops.aludiy.unlink_slot('INVOKE_DEFAULT',True,host_member_id=mid,interface_id=sid)
        except (ReferenceError,RuntimeError,ValidationError) as exc:
            print(f'AluDIY section action cancelled: {exc}')
        finally:g_move._redraw()
        return None
    _PENDING_ACTIONS[window_id]=dispatch
    bpy.app.timers.register(dispatch,first_interval=0.0)


def clear_pending_actions():
    for callback in tuple(_PENDING_ACTIONS.values()):
        if bpy.app.timers.is_registered(callback):bpy.app.timers.unregister(callback)
    _PENDING_ACTIONS.clear()


def modal_inset_guard(context, event):
    """An in-flight modeling transaction cannot click through or retarget the card.

    Esc/right-click cancellation is handled by callers first. Ctrl/navigation
    stay available; move the cursor back to the model before continuing input.
    """
    if event.type in {'ESC','RIGHTMOUSE','LEFT_CTRL','RIGHT_CTRL','MIDDLEMOUSE',
                      'WHEELUPMOUSE','WHEELDOWNMOUSE','TRACKPADPAN','TRACKPADZOOM','TIMER'}:
        return False
    hit = inset_event_hit(context, event)
    if hit:
        hit[0].tag_redraw()
    return hit is not None


def _draw_inspector():
    c = bpy.context
    from . import viewport_overlay as ov
    import gpu
    try:
        view = inspector_layout(c)
        if view is None:
            return
        s=runtime.settings(c.scene);mid=view.member_id;p=view.project
        member=p.members[mid];section=view.profile.section;lay=view.layout
        x,y,w,h=lay.rect.x,lay.rect.y,lay.rect.width,lay.rect.height;u=lay.ui_scale
        gpu.state.blend_set('ALPHA')
        ov._filled_rect(x,y,w,h,(.035,.045,.055,.96))
        ov._text(x+10*u,y+h-22*u,f'{mid} · 点击截面选槽',size=12*u)
        ov._text(x+10*u,y+h-42*u,f'U {section.width_mm:g} × V {section.height_mm:g} mm · {member.roll_deg%360:g}°',size=12*u)
        ov._text(x+10*u,y+h-60*u,'终端看向起端 · 相对 0° 基准',size=10*u)
        points=[]
        for i in range(len(lay.outline)):
            points.extend([lay.outline[i],lay.outline[(i+1)%len(lay.outline)]])
        ov._polyline(points,color=(.85,.93,1,1),width=1.4*u)
        sid=selected_slot(c.scene,mid,p);hover=hovered_slot(c,view)
        for slot in lay.slots:
            active=slot.interface_id==sid;hot=slot.interface_id==hover
            color=(1,.72,.1,1) if active else ((.65,.94,1,1) if hot else (.2,.78,1,1))
            if hot:
                g_move._disc(slot.center,8*u,(.15,.5,.65,.5))
            g_move._disc(slot.center,(4.5 if active or hot else 3)*u,color)
            ov._text(slot.label_rect.x,slot.label_rect.y+3*u,slot.label,size=9*u,color=color)
        disabled=_busy()
        from . import slot_tools
        links=slot_tools.slot_links(p,mid,sid) if sid else ()
        related=slot_tools.selected_links(c,p)
        def short_slot(value):
            return value.replace('FACE_P','+').replace('FACE_N','−').replace('.S','.槽')
        ov._text(x+10*u,y+115*u,('操作中 · ' if disabled else '查看 ') + short_slot(hover or sid or '尚未选槽'),size=11*u,color=(1,.75,.25,1))
        pinned=bool(s.slot_target_member_id)
        target_label=f'定位 {s.slot_target_member_id} / {short_slot(s.slot_target_interface_id)}' if pinned else ('普通吸附 · 已有关联仍保留' if related else '定位：普通吸附')
        try:
            if pinned:slot_tools.target_spec(c.scene,p)
        except Exception:target_label='定位目标失效：请停止后重设'
        ov._text(x+10*u,y+99*u,target_label,size=10*u)
        ov._text(x+10*u,y+83*u,f'此槽关联 {len(links)} 处 / 所选关联 {len(related)} 处',size=10*u)
        controls=((lay.pin_rect,'用于吸附',bool(sid)),
                  (lay.clear_rect,'停止定位',pinned),
                  (lay.create_rect,'创建关联',bool(g_move.engineering_objects(c))),
                  (lay.unlink_rect,'解除所选',bool(related) or bool(g_move.engineering_objects(c))),
                  (lay.unlink_slot_rect,f'解除此槽关联 · {len(links)} 处…',bool(links)))
        for rect,label,enabled in controls:
            enabled=enabled and not disabled
            ov._filled_rect(rect.x,rect.y,rect.width,rect.height,(.17,.27,.34,1) if enabled else (.09,.12,.15,1))
            ov._text(rect.x+8*u,rect.y+9*u,label,size=11*u,
                     color=ov.TEXT_COLOR if enabled else (.42,.48,.51,1))
        # A pinned rail has its own overlay; don't paint it twice.
        same_target=(s.slot_target_member_id==mid and s.slot_target_interface_id==sid)
        if sid and not same_target:
            rail=next(r for r in interface_rails(p,mid,runtime.get_catalog()) if r.interface_id==sid)
            a,b=ov._project(rail.start_mm),ov._project(rail.end_mm)
            if a is not None and b is not None:
                ov._polyline([tuple(a),tuple(b)],color=(1,.67,.1,1),width=3)
                ov.draw_snap_marker(tuple((a+b)*.5),color=(1,.72,.1,1))
    except Exception as exc:
        print(f'AluDIY section inspector: {exc}')
    finally:
        gpu.state.blend_set('NONE')


@bpy.app.handlers.persistent
def _clear_pointer_on_load(_dummy):
    _CURSOR_BY_WINDOW.clear()
    clear_pending_actions()


def register_services():
    global _DRAW_HANDLE
    _CURSOR_BY_WINDOW.clear()
    if _clear_pointer_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_clear_pointer_on_load)
    if _DRAW_HANDLE is None:
        _DRAW_HANDLE=bpy.types.SpaceView3D.draw_handler_add(_draw_inspector,(), 'WINDOW','POST_PIXEL')


def unregister_services():
    global _DRAW_HANDLE
    _CURSOR_BY_WINDOW.clear()
    clear_pending_actions()
    if _clear_pointer_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_clear_pointer_on_load)
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE,'WINDOW');_DRAW_HANDLE=None


CLASSES=(ALUDIY_OT_edit_selected_profiles,ALUDIY_OT_inspect_profile_slot)
