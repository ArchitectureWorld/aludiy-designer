"""Viewport-local command layout and tap classification, no Blender dependency."""
from dataclasses import dataclass
import math
from .section_picker import Rect

ACTIONS = ('MOVE','COPY','DELETE','LINK','UNLINK','JOINTS','PROFILE','TOOLS')

@dataclass(frozen=True)
class WheelLayout:
    rect: Rect
    center: tuple[float,float]
    buttons: tuple
    scale: float
    def hit(self, point):
        return next((key for key,rect in self.buttons if rect.contains(point)),None)


def wheel_layout(point, *, width, height, scale=1.0):
    u = max(.75,min(2.5,float(scale)))
    w,h=352*u,230*u
    if width < w+16*u or height < h+16*u:
        return None
    cx=max(w/2+8*u,min(width-w/2-8*u,float(point[0])))
    cy=max(h/2+8*u,min(height-h/2-8*u,float(point[1])))
    positions=((0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1))
    buttons=tuple((key,Rect(cx+(x*112-52)*u,cy+(y*54-22)*u,104*u,44*u))
                  for key,(x,y) in zip(ACTIONS,positions))
    return WheelLayout(Rect(cx-w/2,cy-h/2,w,h),(cx,cy),buttons,u)


def is_middle_tap(duration, start, end, max_rotation, *, scale=1.0):
    return (0<=duration<=.4 and math.dist(start,end)<=5*scale
            and max_rotation<=.025)
