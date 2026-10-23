"""Read-only section UI geometry and selection values, independent of Blender.

All coordinates are WINDOW-region pixels. Drawing and picking must consume the
same layout. None means the inset is hidden, including its entire hit area.
"""
from dataclasses import dataclass
import math
from .geometry import section_outline_uv
from .geometry import member_length_mm


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self):
        return self.x + self.width / 2, self.y + self.height / 2

    def contains(self, point):
        return self.x <= point[0] < self.x+self.width and self.y <= point[1] < self.y+self.height


@dataclass(frozen=True)
class SlotHit:
    interface_id: str
    center: tuple
    hit_radius: float
    label: str
    label_rect: Rect


@dataclass(frozen=True)
class SectionLayout:
    rect: Rect
    center: tuple
    outline: tuple
    slots: tuple
    pin_rect: Rect
    clear_rect: Rect
    ui_scale: float
    create_rect: Rect
    unlink_rect: Rect
    unlink_slot_rect: Rect
    mode_rect: Rect
    remove_rect: Rect
    clear_selection_rect: Rect

    def hit(self, point):
        if not self.rect.contains(point):
            return None
        for name, rect in (('PIN',self.pin_rect),('CLEAR',self.clear_rect),
                           ('CREATE',self.create_rect),('UNLINK_SELECTED',self.unlink_rect),
                           ('UNLINK_SLOT',self.unlink_slot_rect),('MODE',self.mode_rect),
                           ('REMOVE_SLOT',self.remove_rect),('CLEAR_SELECTION',self.clear_selection_rect)):
            if rect.contains(point):
                return name, ''
        nearby = [(math.dist(s.center,point),s.interface_id) for s in self.slots
                  if math.dist(s.center,point) <= s.hit_radius]
        if nearby:
            return 'SLOT', min(nearby)[1]
        labels = [(math.dist(s.center,point),s.interface_id) for s in self.slots if s.label_rect.contains(point)]
        if labels:
            return 'SLOT', min(labels)[1]
        # Empty parts intentionally consume clicks, without choosing a slot.
        return 'PANEL', ''


def section_layout(section, roll_deg, *, region_width, region_height,
                   visible_right=None, toolbar_width=0, ui_scale=1.0):
    scale_ui = max(.75, min(2.5, float(ui_scale)))
    right = min(region_width, visible_right if visible_right is not None else region_width)
    available = right-toolbar_width-24*scale_ui
    h = 382*scale_ui
    if available < 190*scale_ui or region_height < h+40*scale_ui:
        return None
    w = min(245*scale_ui, available)
    x, y = right-w-12*scale_ui, region_height-h-18*scale_ui
    angle=math.radians(roll_deg);cs,sn=math.cos(angle),math.sin(angle)
    def rotate(uv):return cs*uv[0]-sn*uv[1], sn*uv[0]+cs*uv[1]
    outline=tuple(rotate(uv) for uv in section_outline_uv(section,detailed=True))
    span=max((max(abs(a),abs(b)) for a,b in outline),default=1)
    diagram_scale=min((w-88*scale_ui)/2,35*scale_ui)/max(span,1)
    cx,cy=x+w/2,y+248*scale_ui
    def screen(uv):
        u,v=rotate(uv)
        return cx+diagram_scale*u,cy+diagram_scale*v
    ring=tuple((cx+diagram_scale*u,cy+diagram_scale*v) for u,v in outline)
    raw=[(slot,screen(slot.center_uv_mm)) for slot in sorted(section.interfaces.values(),key=lambda s:s.id)]
    slots=[]
    for slot,pt in raw:
        nearest=min((math.dist(pt,other) for obj,other in raw if obj.id!=slot.id),default=1000)
        radius=min(12*scale_ui,nearest*.42)
        nu,nv=rotate(slot.outward_normal_uv)
        label=slot.host_face_id.replace('FACE_P','+').replace('FACE_N','−')+f'.{slot.lane_index+1}'
        lw,lh=34*scale_ui,15*scale_ui
        tx,ty=pt[0]+nu*15*scale_ui,pt[1]+nv*15*scale_ui
        tx-=lw if nu<-.1 else (lw/2 if abs(nu)<=.1 else 0)
        ty-=lh if nv<-.1 else (lh/2 if abs(nv)<=.1 else 0)
        tx=max(x+4*scale_ui,min(tx,x+w-lw-4*scale_ui))
        slots.append(SlotHit(slot.id,pt,radius,label,Rect(tx,ty,lw,lh)))
    button_w=(w-30*scale_ui)/2
    return SectionLayout(Rect(x,y,w,h),(cx,cy),ring,tuple(slots),
        Rect(x+10*scale_ui,y+81*scale_ui,button_w,24*scale_ui),
        Rect(x+20*scale_ui+button_w,y+81*scale_ui,button_w,24*scale_ui),scale_ui,
        Rect(x+10*scale_ui,y+55*scale_ui,button_w,24*scale_ui),
        Rect(x+20*scale_ui+button_w,y+55*scale_ui,button_w,24*scale_ui),
        Rect(x+10*scale_ui,y+29*scale_ui,w-20*scale_ui,24*scale_ui),
        Rect(x+10*scale_ui,y+107*scale_ui,w-20*scale_ui,22*scale_ui),
        Rect(x+10*scale_ui,y+3*scale_ui,button_w,24*scale_ui),
        Rect(x+20*scale_ui+button_w,y+3*scale_ui,button_w,24*scale_ui))


def selection_readout(project, member_ids, node_ids, *, active_member=None, endpoint=None):
    mids=tuple(sorted(set(member_ids)&project.members.keys()))
    nids=tuple(sorted(set(node_ids)&project.nodes.keys()))
    side=None
    mid=active_member if active_member in mids else (mids[0] if mids else None)
    if endpoint and endpoint[0] in project.members and endpoint[1] in {'START','END'}:
        m=project.members[endpoint[0]]
        nid=m.start_node_id if endpoint[1]=='START' else m.end_node_id
        if not mids and nids==(nid,):mid,side=endpoint
    return dict(member_ids=mids,node_ids=nids,active_member=mid,endpoint=side,
        length_mm=member_length_mm(project,mid) if mid else None,
        lengths=tuple((m,member_length_mm(project,m)) for m in mids),
        node_coordinates=tuple((n,project.nodes[n].position_mm) for n in nids))
