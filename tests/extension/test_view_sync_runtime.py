"""Run actual view-sync functions against minimal Blender RNA stand-ins."""
import importlib.util
import sys
import types
from pathlib import Path
import pytest

@pytest.fixture
def views(monkeypatch):
    bpy=types.ModuleType('bpy'); bpy.__path__=[]
    app=types.ModuleType('bpy.app');app.__path__=[]
    handlers=types.ModuleType('bpy.app.handlers');handlers.persistent=lambda f:f;handlers.load_post=[]
    app.handlers=handlers;bpy.app=app
    pkg=types.ModuleType('view_sync_test');pkg.__path__=[]
    rt=types.ModuleType('view_sync_test.runtime')
    for name in ('AXIS_COLLECTION','HELPER_COLLECTION','SOLID_COLLECTION','WORKSPACE_NAME'):setattr(rt,name,name)
    rt.entity_id_from_object=lambda o:None;rt.settings=lambda s:s
    for name,mod in [('bpy',bpy),('bpy.app',app),('bpy.app.handlers',handlers),('view_sync_test',pkg),('view_sync_test.runtime',rt)]:monkeypatch.setitem(sys.modules,name,mod)
    path=Path(__file__).parents[2]/'extension/aludiy_designer/view_sync.py'
    spec=importlib.util.spec_from_file_location('view_sync_test.view_sync',path)
    mod=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,spec.name,mod);spec.loader.exec_module(mod)
    return mod

def area(projection='PERSP',lens=50,distance=5):
    rv=types.SimpleNamespace(view_rotation=[1,0,0,0],view_location=[.5,1,2],view_distance=distance,
         view_perspective=projection,view_camera_zoom=0,view_camera_offset=[0,0])
    space=types.SimpleNamespace(region_3d=rv,lens=lens,clip_start=.01,clip_end=1000,
                              use_local_camera=False,camera=None)
    return types.SimpleNamespace(spaces=types.SimpleNamespace(active=space),tag_redraw=lambda:None)

@pytest.mark.parametrize('field,value',[('view_perspective','ORTHO'),('view_camera_zoom',42),('view_camera_offset',[.2,.3])])
def test_capture_detects_projection_change_without_orbit(views,field,value):
    a=area();before=views._capture(a);setattr(a.spaces.active.region_3d,field,value)
    assert views._different(before,views._capture(a))

@pytest.mark.parametrize('field,value',[('lens',72),('clip_start',.1),('clip_end',2000),('use_local_camera',True)])
def test_capture_detects_optics_change_without_orbit(views,field,value):
    a=area();before=views._capture(a);setattr(a.spaces.active,field,value)
    assert views._different(before,views._capture(a))

@pytest.mark.parametrize('projection',['PERSP','ORTHO','CAMERA'])
def test_full_sync_includes_projection_optics_and_camera(views,projection):
    a,b=area(projection,72,8),area('ORTHO',33,2)
    a.spaces.active.region_3d.view_camera_offset=[.15,.1];a.spaces.active.region_3d.view_camera_zoom=30
    a.spaces.active.use_local_camera=True
    views._copy_view(a,b,'FULL')
    assert vars(a.spaces.active.region_3d)==vars(b.spaces.active.region_3d)
    assert a.spaces.active.lens==b.spaces.active.lens
    assert a.spaces.active.use_local_camera==b.spaces.active.use_local_camera


def test_orientation_keeps_independent_zoom_but_copies_projection(views):
    a,b=area('PERSP',72,8),area('ORTHO',33,2)
    views._copy_view(a,b,'ORIENTATION')
    assert b.spaces.active.region_3d.view_perspective=='PERSP'
    assert b.spaces.active.region_3d.view_distance==2
    assert b.spaces.active.lens==33


def test_equal_views_do_not_resynchronize(views):
    assert not views._different(views._capture(area()),views._capture(area()))
