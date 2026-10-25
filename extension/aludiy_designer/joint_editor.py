"""Native junction options dialog with a read-only, isolated local body preview.

The preview owns no Blender objects and never rewrites project JSON or mesh
caches. Only the top-level UNDO operator's execute path commits a chosen recipe.
"""
import json
import math
from types import SimpleNamespace
import bpy
from bpy.props import EnumProperty, StringProperty, BoolProperty
from . import runtime, g_move, profile_tools
from .vendor.aludiy_core.errors import ValidationError
from .vendor.aludiy_core.units import parse_distance_mm
from .vendor.aludiy_core.joint_editor import joint_choices, apply_joint_choice
from .vendor.aludiy_core.joints import solve_cutbacks, _body_box

_ACTIVE = None
_HANDLE = None
# Product coordinates in a local clipped envelope; not fake pre-rendered images.
_FACES = ((0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6))
_COLORS = ((.25,.63,.91,1),(.34,.77,.55,1),(.76,.51,.88,1))


def _selection(context):
    spec = g_move.target_spec(context)
    mids = tuple(sorted(spec.get('member_ids', ())))
    if len(mids) not in (2, 3) or spec.get('node_ids') or spec.get('endpoint'):
        raise ValidationError('请选择 2 或 3 根完整型材，再编辑交接；不要只选端点')
    return mids, spec


def _catalog_signature(catalog):
    return json.dumps([profile.to_dict() for profile in catalog], sort_keys=True)


def is_previewing(context):
    return bool(_ACTIVE is not None and context.window and context.scene
                and context.window.as_pointer()==_ACTIVE.window_id
                and context.scene.as_pointer()==_ACTIVE.scene_id)


def _redraw():
    g_move._redraw()


def clear_preview():
    global _ACTIVE, _HANDLE
    if _ACTIVE is not None:
        # UI-only temporary changes are restored even on cancellation/load/disable.
        try:
            w=next((w for w in bpy.context.window_manager.windows if w.as_pointer()==_ACTIVE.window_id),None)
            if w and w.screen.as_pointer()==_ACTIVE.screen_id:
                for a in w.screen.areas:
                    if a.as_pointer() in _ACTIVE.sidebars and a.type=='VIEW_3D':
                        a.spaces.active.show_region_ui=_ACTIVE.sidebars[a.as_pointer()]
        except (ReferenceError,RuntimeError):
            pass
        _ACTIVE.owner = None
    _ACTIVE = None
    if _HANDLE is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_HANDLE, 'WINDOW')
        except (ValueError, ReferenceError, RuntimeError):
            pass
        _HANDLE = None
    _redraw()


def _watch():
    if _ACTIVE is None:
        return None
    try:
        window = next((w for w in bpy.context.window_manager.windows
                       if w.as_pointer() == _ACTIVE.window_id), None)
        if window is None or window.scene.as_pointer() != _ACTIVE.scene_id:
            clear_preview(); return None
    except (ReferenceError, RuntimeError):
        clear_preview(); return None
    return .2


@bpy.app.handlers.persistent
def _on_load(_):
    clear_preview()


def _focus(project, ids):
    # Among endpoints, choose the point closest to every other design segment.
    points = [project.nodes[n].position_mm for mid in ids for n in
              (project.members[mid].start_node_id, project.members[mid].end_node_id)]
    def distance(p):
        total = 0.
        for mid in ids:
            m = project.members[mid];a=project.nodes[m.start_node_id].position_mm;b=project.nodes[m.end_node_id].position_mm
            d=tuple(b[i]-a[i] for i in range(3));den=sum(x*x for x in d)
            t=max(0.,min(1.,sum((p[i]-a[i])*d[i] for i in range(3))/den))
            total += math.dist(p,tuple(a[i]+t*d[i] for i in range(3)))
        return total
    return min(points, key=distance)


def _preview_shapes(session):
    """Crop only the displayed far ends; actual engineering lengths remain full."""
    option = session.option
    project = (option.project if option and option.valid and not session.before else session.source)
    catalog = session.catalog;ids=session.member_ids
    result = solve_cutbacks(project, catalog)
    offsets = {(mid, side): getattr(v, 'start_setback_mm' if side=='START' else 'end_setback_mm')
               for mid,v in result.lengths.items() for side in ('START','END')} if not result.issues else {}
    focus = session.focus
    max_size = max(max(catalog.get(project.members[mid].profile_type_id).section.width_mm,
                       catalog.get(project.members[mid].profile_type_id).section.height_mm) for mid in ids)
    radius = max(70., max_size*3, min(250., abs(session.gap_mm)*2+30))
    shapes = []
    from itertools import product
    for mid in ids:
        center, axes, half = _body_box(project, catalog, mid, offsets)
        t = sum((focus[i]-center[i])*axes[2][i] for i in range(3))
        lo=max(-half[2],t-radius);hi=min(half[2],t+radius)
        if hi<=lo:
            continue
        center=tuple(center[i]+axes[2][i]*(hi+lo)/2-focus[i] for i in range(3))
        half=(half[0],half[1],(hi-lo)/2)
        verts=tuple(tuple(center[i]+sum(s[j]*half[j]*axes[j][i] for j in range(3))
                          for i in range(3)) for s in product((-1,1),repeat=3))
        shapes.append((mid,verts))
    return shapes


def _draw_preview():
    import gpu
    from gpu_extras.batch import batch_for_shader
    from . import viewport_overlay as ov
    session = _ACTIVE
    c=bpy.context
    if (session is None or not c.window or c.window.as_pointer()!=session.window_id
            or c.scene.as_pointer()!=session.scene_id or not c.area or c.area.type!='VIEW_3D'
            or not c.region or c.region.type!='WINDOW'):
        return
    try:
        u=max(.75,min(2.5,c.preferences.system.ui_scale))
        right=c.region.width
        sidebar=next((r for r in c.area.regions if r.type=='UI'),None)
        if c.space_data.show_region_ui and sidebar and sidebar.width>1:
            right=min(right,sidebar.x-c.region.x)
        toolbar=next((r for r in c.area.regions if r.type=='TOOLS'),None)
        left=max(0,toolbar.x+toolbar.width-c.region.x) if toolbar and c.space_data.show_region_toolbar else 0
        width=min(380*u,right-left-24*u);height=min(340*u,c.region.height-50*u)
        if width<230*u or height<200*u:
            return
        x=left+12*u;y=24*u
        gpu.state.blend_set('ALPHA')
        ov._filled_rect(x,y,width,height,(.035,.05,.065,1.))
        title='修改前' if session.before else ('方案预览' if session.option and session.option.valid else '当前几何 · 方案不可用')
        ov._text(x+12*u,y+height-24*u,f'交接局部预览 · {title}',size=13*u)
        if session.option:
            ov._text(x+12*u,y+height-44*u,f'贯通杆 {session.option.host_member_id}（金色）',size=11*u,color=(1.,.74,.28,1))
        shapes=_preview_shapes(session)
        angle=session.view_angle
        if angle=='TOP':right_axis=(1,0,0);up=(0,1,0);depth=(0,0,1)
        elif angle=='FRONT':right_axis=(1,0,0);up=(0,0,1);depth=(0,-1,0)
        elif angle=='SIDE':right_axis=(0,1,0);up=(0,0,1);depth=(1,0,0)
        else:
            right_axis=(.70710678,.70710678,0);up=(-.40824829,.40824829,.81649658);depth=(.57735027,-.57735027,.57735027)
        def project(p):return (sum(a*b for a,b in zip(p,right_axis)),sum(a*b for a,b in zip(p,up)),sum(a*b for a,b in zip(p,depth)))
        screen={mid:[project(v) for v in verts] for mid,verts in shapes}
        allpts=[p for vs in screen.values() for p in vs]
        if not allpts:return
        minx=min(p[0] for p in allpts);maxx=max(p[0] for p in allpts)
        miny=min(p[1] for p in allpts);maxy=max(p[1] for p in allpts)
        factor=min((width-46*u)/max(1.,maxx-minx),(height-113*u)/max(1.,maxy-miny))
        cx=x+width/2;cy=y+(height-55*u)/2
        def to2(p):return (cx+(p[0]-(minx+maxx)/2)*factor,cy+(p[1]-(miny+maxy)/2)*factor)
        shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        polygons=[]
        for mid, vs in screen.items():
            base=(1.,.65,.18,1.) if session.option and mid==session.option.host_member_id else _COLORS[session.member_ids.index(mid)]
            for fi,face in enumerate(_FACES):
                p2=[to2(vs[i]) for i in face]
                polygons.append((sum(vs[i][2] for i in face)/4,p2,base,fi))
        for _,poly,color,fi in sorted(polygons,key=lambda item:item[0]):
            shade=(.78,.98,.68,.90,.82,1.)[fi]
            shader.bind();shader.uniform_float('color',tuple(v*shade for v in color[:3])+(1.,))
            batch_for_shader(shader,'TRIS',{'pos':poly},indices=((0,1,2),(0,2,3))).draw(shader)
            shader.uniform_float('color',(.07,.10,.14,1))
            batch_for_shader(shader,'LINE_STRIP',{'pos':poly+[poly[0]]}).draw(shader)
        # Labels identify roles without putting static dimension lines on the model.
        labels=' / '.join(f'{m}{" 主" if session.option and m==session.option.host_member_id else " 支"}' for m in session.member_ids)
        ov._text(x+12*u,y+30*u,labels,size=10*u)
        ov._text(x+12*u,y+12*u,'截取局部矩形外廓 · 未验证连接件/装配',size=9*u,color=(.65,.70,.75,1))
    except Exception as exc:
        if not getattr(session,'draw_error',False):
            print(f'AluDIY joint preview: {exc}');session.draw_error=True
    finally:
        gpu.state.blend_set('NONE')


class ALUDIY_OT_edit_joint_options(bpy.types.Operator):
    bl_idname='aludiy.edit_joint_options'
    bl_label='交接方案编辑 · L / T / 三向'
    bl_description='选2或3根型材，比较贯通方案与局部预览；确认前不改变工程，设计线和位置关联不动'
    bl_options={'REGISTER','UNDO'}
    host_choice: EnumProperty(items=(('A','方案 A',''),('B','方案 B',''),('C','方案 C','')),default='A')
    host_member_id: StringProperty(default='',options={'HIDDEN'})
    member_ids_json: StringProperty(default='',options={'HIDDEN'})
    gap_input: StringProperty(name='端面间隙',default='0',description='默认毫米，支持2mm / 0.002m / 算式；必须非负')
    before: BoolProperty(name='对比修改前',default=False)
    view_angle: EnumProperty(name='观察方向',items=(('ISO','轴测',''),('TOP','俯视',''),('FRONT','正视',''),('SIDE','侧视','')),default='ISO')

    @classmethod
    def poll(cls,context):
        # Native confirmation polls again. Let execute reject stale selection
        # and run its cleanup instead of silently leaving the preview alive.
        if _ACTIVE is not None:
            return True
        if context.mode!='OBJECT' or profile_tools._busy():
            return False
        try:_selection(context);return True
        except Exception:return False

    def _refresh(self,context):
        session=self._session
        session.before=self.before;session.view_angle=self.view_angle
        self._error=''
        try:
            session.gap_mm=parse_distance_mm(self.gap_input)
            self._choices=joint_choices(session.source,session.catalog,member_ids=session.member_ids,gap_mm=session.gap_mm)
            index='ABC'.index(self.host_choice)
            if index>=len(self._choices):raise ValidationError('当前选区没有第三个贯通方案')
            session.option=self._choices[index];self.host_member_id=session.option.host_member_id
            if not session.option.valid:self._error=session.option.message
        except Exception as exc:
            self._choices=();session.option=None;self._error=str(exc)
        _redraw()

    def invoke(self,context,event):
        global _ACTIVE,_HANDLE
        if _ACTIVE is not None:
            self.report({'WARNING'},'请先结束当前交接编辑')
            return {'CANCELLED'}
        try:
            ids,spec=_selection(context)
            source=runtime.get_project(context.scene);catalog=runtime.get_catalog()
            self.member_ids_json=json.dumps(ids)
            self.gap_input=runtime.settings(context.scene).joint_gap_input
            local=[j for j in source.joints.values() if j.host_member_id in ids and j.branch_member_id in ids]
            if local and len({j.gap_mm for j in local})==1:self.gap_input=f'{local[0].gap_mm:g}'
            choices=joint_choices(source,catalog,member_ids=ids,gap_mm=parse_distance_mm(self.gap_input))
            requested=self.host_member_id or (local[0].host_member_id if local and len({j.host_member_id for j in local})==1 else runtime.entity_id_from_object(context.view_layer.objects.active))
            index=next((i for i,o in enumerate(choices) if o.valid and o.host_member_id==requested),None)
            if index is None:index=next((i for i,o in enumerate(choices) if o.valid),0)
            self.host_choice='ABC'[index]
            self._session=SimpleNamespace(source=source,catalog=catalog,member_ids=ids,spec=spec,
                raw=runtime.settings(context.scene).project_json,catalog_signature=_catalog_signature(catalog),
                scene_id=context.scene.as_pointer(),window_id=context.window.as_pointer(),
                screen_id=context.window.screen.as_pointer(),sidebars={},
                owner=self,option=None,before=False,view_angle='ISO',gap_mm=0.,focus=_focus(source,ids),draw_error=False)
            self._refresh(context)
            _ACTIVE=self._session
            for a in context.window.screen.areas:
                if a.type=='VIEW_3D' and a!=context.area:
                    _ACTIVE.sidebars[a.as_pointer()]=a.spaces.active.show_region_ui
                    a.spaces.active.show_region_ui=False
            _HANDLE=bpy.types.SpaceView3D.draw_handler_add(_draw_preview,(),'WINDOW','POST_PIXEL')
            if not bpy.app.timers.is_registered(_watch):bpy.app.timers.register(_watch,first_interval=.2)
            return context.window_manager.invoke_props_dialog(self,width=465,confirm_text='应用交接方案')
        except Exception as exc:
            clear_preview();self.report({'WARNING'},str(exc));return {'CANCELLED'}

    def check(self,context):
        if _ACTIVE is not None and getattr(self,'_session',None) is _ACTIVE:self._refresh(context)
        return True

    def draw(self,context):
        layout=self.layout
        layout.label(text='设计线固定 · 只改变实体收头 · 未匹配连接件',icon='INFO')
        choices=getattr(self,'_choices',())
        for i,choice in enumerate(choices):
            row=layout.row();row.enabled=choice.valid
            label=f'{"ABC"[i]} · {choice.host_member_id} 贯通'
            if choice.valid:label+=f'  /  {"三向角点" if choice.kind=="CORNER3" else choice.kind+" 形"}'
            else:label+='  /  不可用'
            row.prop_enum(self,'host_choice','ABC'[i],text=label)
            if not choice.valid:
                for k in range(0,min(len(choice.message),90),32):layout.label(text=choice.message[k:k+32],icon='BLANK1')
        layout.prop(self,'gap_input')
        row=layout.row(align=True);row.prop(self,'before',toggle=True);row.prop(self,'view_angle',text='')
        err=getattr(self,'_error','')
        session=getattr(self,'_session',None)
        if err:
            box=layout.box();box.alert=True
            for k in range(0,len(err),32):box.label(text=err[k:k+32],icon='ERROR' if k==0 else 'BLANK1')
            layout.label(text='当前方案不能提交；修改间隙或取消后调整构件')
        elif session and session.option and session.option.valid:
            option=session.option
            box=layout.box()
            box.label(text='杆件       设计线 / 实体参考长度       起端 / 终端退让')
            for mid in session.member_ids:
                v=option.solution.lengths[mid]
                box.label(text=f'{mid}  {v.design_length_mm:g} / {v.cut_length_mm:g} mm    {v.start_setback_mm:g} / {v.end_setback_mm:g}',icon='MOD_LENGTH')
            a,b=option.before_bounds,option.after_bounds
            box=layout.box();box.label(text='所选组世界外包络（非家具外尺寸约束）')
            for i,name in enumerate('XYZ'):
                old=a[1][i]-a[0][i];new=b[1][i]-b[0][i]
                box.label(text=f'{name}  {old:g} → {new:g} mm  / Δ {new-old:+g}')
            box.label(text='包络面位移：低 / 高（mm）')
            for i,name in enumerate('XYZ'):
                box.label(text=f'{name}  {b[0][i]-a[0][i]:+g} / {b[1][i]-a[1][i]:+g}')
            layout.label(text='局部外廓检查通过；不代表全模型/配件/工具空间已核验')
        layout.label(text='预览位于模型区左下角；确认写入，取消零改动')

    def execute(self,context):
        try:
            session=getattr(self,'_session',None)
            if session is not None:
                if (context.mode!='OBJECT' or session is not _ACTIVE or context.scene.as_pointer()!=session.scene_id
                        or runtime.settings(context.scene).project_json!=session.raw
                        or g_move.target_spec(context)!=session.spec
                        or _catalog_signature(runtime.get_catalog())!=session.catalog_signature):
                    raise ValidationError('工程、选择或目录已改变，请重新打开交接编辑器')
                if self._error:raise ValidationError(self._error)
                spec=session.spec;ids=session.member_ids
            else:
                ids,spec=_selection(context)
                if self.member_ids_json and tuple(json.loads(self.member_ids_json))!=ids:
                    raise ValidationError('交接对象选择已变化，请重新打开编辑器')
            p=runtime.get_project(context.scene)
            r=apply_joint_choice(p,runtime.get_catalog(),member_ids=ids,
                host_member_id=self.host_member_id,gap_mm=parse_distance_mm(self.gap_input))
            if not r.changed_count:
                runtime.set_status(context.scene,'交接方案未改变');return {'CANCELLED'}
            g_move._commit_relations(context,p,r.project,spec)
            runtime.set_status(context.scene,f'已应用 {len(ids)} 杆交接 · {self.host_member_id} 贯通 · 设计线/位置关联不变 · 未验证装配')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'WARNING'},str(exc));return {'CANCELLED'}
        finally:
            # Native Undo stores operator properties, not a stale preview session.
            if hasattr(self,'_session'):del self._session
            clear_preview()

    def cancel(self,context):
        if hasattr(self,'_session'):del self._session
        clear_preview()


def register_services():
    if _on_load not in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.append(_on_load)


def unregister_services():
    clear_preview()
    if bpy.app.timers.is_registered(_watch):bpy.app.timers.unregister(_watch)
    if _on_load in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(_on_load)


CLASSES=(ALUDIY_OT_edit_joint_options,)
