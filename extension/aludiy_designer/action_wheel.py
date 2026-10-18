"""Cursor-local engineering commands; native MMB orbit is wrapped, not replaced.

A macro runs Blender's view3d.rotate with the original press/release events.
Only a short stationary gesture opens the wheel after navigation has finished.
Model operations are dispatched after this non-Undo UI operator has closed.
"""
import math
import time
import bpy
from bpy.props import FloatVectorProperty
from . import runtime, g_move, operators, profile_tools, selection_state, view_sync
from .vendor.aludiy_core.action_wheel import wheel_layout, is_middle_tap

_WHEEL = None
_GESTURES = {}
_PENDING = {}
_KEYMAPS = []
_DRAW_HANDLE = None
_ENABLED = False
_MACRO_DEFINED = False
_LABELS = dict(MOVE='移动  G', COPY='复制  Shift+D', DELETE='删除…', LINK='创建关联',
               UNLINK='解除关联', JOINTS='交接处理 ›', PROFILE='截面 / 规格 ›', TOOLS='端点 / 画线 ›')


def _scale(context):
    return max(.75, min(2.5, context.preferences.system.ui_scale))


def _scope(context):
    return (context.window and context.area and context.area.type=='VIEW_3D'
            and context.region and context.region.type=='WINDOW'
            and context.workspace.name==runtime.WORKSPACE_NAME and context.mode=='OBJECT')


def _busy():
    return g_move._ACTIVE is not None or operators._ACTIVE_DRAW is not None


def _signature(context):
    selected, active = selection_state.capture(context)
    return (frozenset((x[0],x[1]) for x in selected),
            (active[0],active[1]) if active else None)


def _allowed(context):
    mids, nids = g_move.selection_summary(context)
    objects = g_move.selected_objects(context)
    pure = len(objects)==len(g_move.engineering_objects(context))
    return dict(MOVE=pure and bool(mids or nids), COPY=pure and bool(mids),
                DELETE=pure and bool(mids), LINK=pure and bool(mids or nids),
                UNLINK=pure and bool(mids or nids), JOINTS=pure and bool(mids),
                PROFILE=pure and bool(mids), TOOLS=pure)


def _queue(context, action, point=None):
    """Guard a deferred top-level operator invocation; never capture stale RNA."""
    key=context.window.as_pointer()
    if key in _PENDING:return
    area_id, scene_id=context.area.as_pointer(),context.scene.as_pointer()
    raw=runtime.settings(context.scene).project_json
    selection=_signature(context)
    target=(runtime.settings(context.scene).slot_target_member_id,
            runtime.settings(context.scene).slot_target_interface_id)
    def dispatch():
        _PENDING.pop(key,None)
        try:
            if not _ENABLED:return None
            window=next((w for w in bpy.context.window_manager.windows if w.as_pointer()==key),None)
            if window is None or window.scene.as_pointer()!=scene_id:return None
            area=next((a for a in window.screen.areas if a.as_pointer()==area_id and a.type=='VIEW_3D'),None)
            if area is None:return None
            region=g_move._window_region(area)
            if region is None:return None
            with bpy.context.temp_override(window=window,area=area,region=region):
                c=bpy.context;s=runtime.settings(c.scene)
                if (not _scope(c) or _busy() or s.project_json!=raw or _signature(c)!=selection
                        or (s.slot_target_member_id,s.slot_target_interface_id)!=target):
                    return None
                if action=='OPEN':
                    bpy.ops.aludiy.action_wheel('INVOKE_DEFAULT',location=point)
                elif not _allowed(c).get(action,False):
                    return None
                elif action in {'MOVE','COPY'}:
                    bpy.ops.aludiy.move_engineering('INVOKE_DEFAULT',True,duplicate=action=='COPY',connect_only=False)
                elif action=='DELETE':
                    bpy.ops.aludiy.delete_selected_members('INVOKE_DEFAULT',True)
                elif action=='LINK':
                    bpy.ops.aludiy.create_associations('EXEC_DEFAULT',True)
                elif action=='UNLINK':
                    bpy.ops.aludiy.remove_associations('EXEC_DEFAULT',True)
                else:
                    menu={'JOINTS':'ALUDIY_MT_wheel_joints','PROFILE':'ALUDIY_MT_wheel_profiles','TOOLS':'ALUDIY_MT_wheel_tools'}[action]
                    bpy.ops.wm.call_menu('INVOKE_DEFAULT',name=menu)
        except (ReferenceError,RuntimeError,ValueError) as exc:
            print(f'AluDIY action wheel: {exc}')
        finally:g_move._redraw()
        return None
    _PENDING[key]=dispatch
    bpy.app.timers.register(dispatch,first_interval=0)


def _view_snapshot(rv):
    return tuple(rv.view_rotation),tuple(rv.view_location),rv.view_distance,rv.view_perspective


def _angle(a,b):
    return 2*math.acos(min(1.,abs(sum(float(x)*float(y) for x,y in zip(a,b)))))


class ALUDIY_OT_middle_begin(bpy.types.Operator):
    bl_idname='aludiy.middle_begin'
    bl_label='识别中键手势'
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        if profile_tools.inset_event_hit(context,event):return {'CANCELLED'}
        key=context.window.as_pointer()
        rv=context.region_data
        record=dict(start=(event.mouse_x,event.mouse_y),time=time.monotonic(),
                    view=_view_snapshot(rv),max_angle=0.,area_id=context.area.as_pointer())
        previous=_GESTURES.pop(key,None)
        if previous and bpy.app.timers.is_registered(previous['timer']):
            bpy.app.timers.unregister(previous['timer'])
        _GESTURES[key]=record
        def observe():
            if not _ENABLED or _GESTURES.get(key) is not record:return None
            # Esc cancels the native rotate child, so the macro finish may not run.
            # After the tap window expires the gesture can no longer open a menu.
            if time.monotonic()-record['time']>.45:
                _GESTURES.pop(key,None)
                return None
            try:
                record['max_angle']=max(record['max_angle'],_angle(record['view'][0],rv.view_rotation))
            except ReferenceError:
                _GESTURES.pop(key,None)
                return None
            return .016
        record['timer']=observe
        bpy.app.timers.register(observe,first_interval=.016)
        return {'FINISHED'}


class ALUDIY_OT_middle_finish(bpy.types.Operator):
    bl_idname='aludiy.middle_finish'
    bl_label='中键轻点操作盘'
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        record=_GESTURES.pop(context.window.as_pointer(),None)
        if not record:return {'CANCELLED'}
        timer=record['timer']
        if bpy.app.timers.is_registered(timer):bpy.app.timers.unregister(timer)
        rv=context.region_data
        angle=max(record['max_angle'],_angle(record['view'][0],rv.view_rotation))
        tap=is_middle_tap(time.monotonic()-record['time'],record['start'],(event.mouse_x,event.mouse_y),angle,scale=_scale(context))
        if tap and _scope(context) and not _busy():
            # Native navigation can enable perspective on press. A tap should not.
            rotation,location,distance,perspective=record['view']
            rv.view_rotation=rotation;rv.view_location=location
            rv.view_distance=distance;rv.view_perspective=perspective
            view_sync._sync_window(context.window)
            _queue(context,'OPEN',(event.mouse_x-context.region.x,event.mouse_y-context.region.y))
        return {'FINISHED'}


class ALUDIY_OT_middle_context(bpy.types.Macro):
    bl_idname='aludiy.middle_context'
    bl_label='中键轻点操作盘 / 拖动旋转'
    @classmethod
    def poll(cls,context):
        return bool(_ENABLED and _WHEEL is None and _scope(context) and not _busy()
                    and bpy.ops.view3d.rotate.poll())


class ALUDIY_OT_action_wheel(bpy.types.Operator):
    bl_idname='aludiy.action_wheel'
    bl_label='模型操作盘'
    bl_description='中键轻点弹出；中键/右键/Esc关闭，左键盘外仅关闭；拖动中键仍旋转视图'
    location: FloatVectorProperty(size=2,default=(-1,-1),options={'HIDDEN','SKIP_SAVE'})
    @classmethod
    def poll(cls,context):
        return bool(_scope(context) and not _busy() and _WHEEL is None)
    def invoke(self,context,event):
        global _WHEEL
        self._closed=False
        self._area=context.area;self._window=context.window;self._scene=context.scene
        self._region=context.region;self._raw=runtime.settings(context.scene).project_json
        self._selection=_signature(context)
        self._mouse=(event.mouse_x-context.region.x,event.mouse_y-context.region.y)
        point=tuple(self.location) if self.location[0]>=0 else self._mouse
        right=context.region.width
        sidebar=next((r for r in context.area.regions if r.type=='UI'),None)
        if context.space_data.show_region_ui and sidebar and sidebar.width>1:
            right=min(right,sidebar.x-context.region.x)
        self._layout=wheel_layout(point,width=right,height=context.region.height,scale=_scale(context))
        if self._layout is None:
            self.report({'INFO'},'视窗太小，收起侧栏或放大视窗后再打开操作盘')
            return {'CANCELLED'}
        _WHEEL=self
        self._dismiss_button=None
        context.window_manager.modal_handler_add(self)
        g_move._redraw()
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if self._closed:return {'CANCELLED'}
        if (context.window!=self._window or context.scene!=self._scene or not _scope(context)
                or runtime.settings(self._scene).project_json!=self._raw or _signature(context)!=self._selection):
            self.cancel(context);return {'CANCELLED'}
        if self._dismiss_button:
            if event.type==self._dismiss_button and event.value=='RELEASE':
                self.cancel(context);return {'CANCELLED'}
            return {'RUNNING_MODAL'}
        self._mouse=(event.mouse_x-self._region.x,event.mouse_y-self._region.y)
        if event.type=='ESC' and event.value=='PRESS':
            self.cancel(context);return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE','RIGHTMOUSE'} and event.value=='PRESS':
            self._dismiss_button=event.type;g_move._redraw();return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            action=self._layout.hit(self._mouse)
            if action and _allowed(context).get(action,False):
                self.cancel(context)
                _queue(context,action)
                return {'FINISHED'}
            # Swallow both halves of the closing click, including click-select keymaps.
            self._dismiss_button='LEFTMOUSE';g_move._redraw()
            return {'RUNNING_MODAL'}
        g_move._redraw()
        return {'RUNNING_MODAL'}
    def cancel(self,context):
        global _WHEEL
        self._closed=True
        if _WHEEL is self:_WHEEL=None
        g_move._redraw()


def _draw():
    op=_WHEEL;c=bpy.context
    if not op or op._closed or op._dismiss_button or c.area!=op._area or c.window!=op._window:return
    from . import viewport_overlay as ov
    import gpu
    try:
        lay=op._layout;u=lay.scale;r=lay.rect
        gpu.state.blend_set('ALPHA')
        ov._filled_rect(r.x,r.y,r.width,r.height,(.055,.06,.07,.98))
        ov._text(r.x+12*u,r.y+r.height-22*u,'ALU DIY · 模型操作',size=12*u)
        hot=lay.hit(op._mouse);allowed=_allowed(c)
        for name,rect in lay.buttons:
            enabled=allowed[name]
            color=(.25,.32,.38,1) if enabled and hot==name else ((.15,.17,.19,1) if enabled else (.085,.095,.105,1))
            ov._filled_rect(rect.x,rect.y,rect.width,rect.height,color)
            text=(.93,.94,.95,1) if enabled else (.37,.40,.44,1)
            if name=='DELETE' and enabled:text=(1,.65,.58,1)
            ov._text(rect.x+9*u,rect.y+17*u,_LABELS[name],size=11*u,color=text)
        mids,nids=g_move.selection_summary(c);cx,cy=lay.center
        ov._text(cx-37*u,cy+7*u,f'已选 {len(mids)} 根',size=12*u)
        ov._text(cx-37*u,cy-12*u,f'{len(nids)} 个节点',size=10*u)
        ov._text(r.x+12*u,r.y+13*u,'中键 / Esc 关闭 · 盘外点击只关闭',size=10*u,color=(.6,.64,.69,1))
    finally:gpu.state.blend_set('NONE')


class ALUDIY_MT_wheel_joints(bpy.types.Menu):
    bl_label='交接处理'
    def draw(self,context):
        from . import joint_tools
        self.layout.operator_context='INVOKE_REGION_WIN'
        joint_tools.draw_panel(self.layout,context)


class ALUDIY_MT_wheel_profiles(bpy.types.Menu):
    bl_label='型材规格与截面'
    def draw(self,context):
        self.layout.operator_context='INVOKE_REGION_WIN'
        profile_tools.draw_panel(self.layout,context)


class ALUDIY_MT_wheel_tools(bpy.types.Menu):
    bl_label='端点与精确建模'
    def draw(self,context):
        l=self.layout;l.operator_context='INVOKE_REGION_WIN'
        l.operator('aludiy.select_endpoint',text='选择起端（绿）').endpoint='START'
        l.operator('aludiy.select_endpoint',text='选择终端（红）').endpoint='END'
        l.separator()
        l.operator('aludiy.draw_member',text='连续画线')
        l.operator('aludiy.translate_active_member',text='精确平移 ΔXYZ')
        s=runtime.settings(context.scene)
        l.prop(s,'length_input');l.prop(s,'resize_anchor')
        l.operator('aludiy.resize_active_member',text='调整设计长度')
        l.separator();l.operator('aludiy.rebuild_scene',text='从工程数据重建视图')


@bpy.app.handlers.persistent
def _clear(_dummy=None):
    global _WHEEL
    if _WHEEL is not None:
        _WHEEL._closed=True;_WHEEL=None
    callbacks=list(_PENDING.values())+[x['timer'] for x in _GESTURES.values()]
    _PENDING.clear();_GESTURES.clear()
    for callback in callbacks:
        if bpy.app.timers.is_registered(callback):bpy.app.timers.unregister(callback)


def register_services():
    global _DRAW_HANDLE,_ENABLED,_MACRO_DEFINED
    _ENABLED=True
    if not _MACRO_DEFINED:
        ALUDIY_OT_middle_context.define('ALUDIY_OT_middle_begin')
        ALUDIY_OT_middle_context.define('VIEW3D_OT_rotate')
        ALUDIY_OT_middle_context.define('ALUDIY_OT_middle_finish')
        _MACRO_DEFINED=True
    kc=bpy.context.window_manager.keyconfigs.addon
    if kc and not _KEYMAPS:
        km=kc.keymaps.new(name='3D View',space_type='VIEW_3D')
        _KEYMAPS.append((km,km.keymap_items.new('aludiy.middle_context',type='MIDDLEMOUSE',value='PRESS',head=True)))
    if _DRAW_HANDLE is None and not bpy.app.background:
        _DRAW_HANDLE=bpy.types.SpaceView3D.draw_handler_add(_draw,(),'WINDOW','POST_PIXEL')
    if _clear not in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.append(_clear)


def unregister_services():
    global _DRAW_HANDLE,_ENABLED,_MACRO_DEFINED
    _ENABLED=False;_clear()
    for km,kmi in reversed(_KEYMAPS):
        try:km.keymap_items.remove(kmi)
        except (ReferenceError,RuntimeError):pass
    _KEYMAPS.clear()
    if _clear in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(_clear)
    if _DRAW_HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_DRAW_HANDLE,'WINDOW');_DRAW_HANDLE=None
    _MACRO_DEFINED=False

CLASSES=(ALUDIY_OT_middle_begin,ALUDIY_OT_middle_finish,ALUDIY_OT_middle_context,
         ALUDIY_OT_action_wheel,ALUDIY_MT_wheel_joints,ALUDIY_MT_wheel_profiles,ALUDIY_MT_wheel_tools)
