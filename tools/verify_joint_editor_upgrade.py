#!/usr/bin/env python3
"""Isolated install-over-install check with an old saved project, no uninstall.

Uses Blender's official extension CLI. Never writes the user's real preferences.
"""
import argparse, json, os, pathlib, subprocess
p=argparse.ArgumentParser();p.add_argument('blender');p.add_argument('old_zip');p.add_argument('new_zip');p.add_argument('output');args=p.parse_args()
out=pathlib.Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,BLENDER_USER_CONFIG=str(out/'config'),BLENDER_USER_EXTENSIONS=str(out/'extensions'),LIBGL_ALWAYS_SOFTWARE='1')
repo=out/'repository'

def run(name,cmd):
    r=subprocess.run([args.blender,*cmd],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=80)
    (out/(name+'.log')).write_text(r.stdout)
    if r.returncode:raise RuntimeError(f'{name} exited {r.returncode}: {r.stdout[-2000:]}')
    return r.stdout

run('repo',['--command','extension','repo-add','aludiy_upgrade','--directory',str(repo),'--clear-all'])
run('install-old',['--command','extension','install-file','-r','aludiy_upgrade','-e',str(pathlib.Path(args.old_zip).resolve())])
create=out/'create-old.py';create.write_text('''import bpy,json
from bl_ext.aludiy_upgrade.aludiy_designer import runtime
from bl_ext.aludiy_upgrade.aludiy_designer.vendor.aludiy_core import Project,Node,Member
p=Project('P-UPGRADE','alpha-2026.10')
p.add_node(Node('N-1',(0,0,0)));p.add_node(Node('N-2',(0,0,800)))
p.add_member(Member('M-1','N-1','N-2','generic:tslot-2040@0.1',roll_deg=45))
from bl_ext.aludiy_upgrade.aludiy_designer.vendor.aludiy_core.profile_editing import interface_rails
from bl_ext.aludiy_upgrade.aludiy_designer.vendor.aludiy_core.associations import create_slot_associations
rail=next(r for r in interface_rails(p,'M-1',runtime.get_catalog()) if r.interface_id=='FACE_PV.S1')
pt=tuple((rail.start_mm[i]+rail.end_mm[i])/2 for i in range(3))
p.add_node(Node('N-3',pt));p.add_node(Node('N-4',(pt[0]+400,pt[1],pt[2])))
p.add_member(Member('M-2','N-3','N-4','generic:tslot-2020@0.1'))
p=create_slot_associations(p,runtime.get_catalog(),host_member_id='M-1',interface_id='FACE_PV.S1',node_ids=['N-3']).project
assert p.schema_version=='0.3.0'
runtime.set_project(bpy.context.scene,p)
assert runtime.EXTENSION_VERSION=='0.1.19-alpha'
open('''+repr(str(out/'expected.json'))+''','w').write(json.dumps(p.to_dict()))
bpy.ops.wm.save_as_mainfile(filepath='''+repr(str(out/'old.blend'))+''')
print('OLD_PROJECT_CREATED')
''')
run('old-save',['-b','--python-exit-code','1','--python',str(create)])
run('install-new',['--command','extension','install-file','-r','aludiy_upgrade','-e',str(pathlib.Path(args.new_zip).resolve())])
check=out/'verify-new.py';check.write_text('''import bpy,json
from bl_ext.aludiy_upgrade.aludiy_designer import runtime
assert runtime.EXTENSION_VERSION=='0.1.20-alpha'
assert runtime.get_project(bpy.context.scene).to_dict()==json.load(open('''+repr(str(out/'expected.json'))+'''))
assert hasattr(bpy.ops.aludiy,'inspect_profile_slot')
assert hasattr(runtime.settings(bpy.context.scene),'joint_gap_input')
assert hasattr(bpy.ops.aludiy,'unlink_slot')
assert hasattr(bpy.ops.aludiy,'set_butt_joint')
assert 'duplicate' in bpy.ops.aludiy.move_engineering.get_rna_type().properties
assert hasattr(bpy.ops.aludiy,'action_wheel')
from bl_ext.aludiy_upgrade.aludiy_designer import slot_tools
from bl_ext.aludiy_upgrade.aludiy_designer.vendor.aludiy_core.slot_selection import make_target,encode_targets
scene=bpy.context.scene;project=runtime.get_project(scene);settings=runtime.settings(scene)
assert not settings.slot_only
records=tuple(make_target(project,runtime.get_catalog(),'M-1',sid) for sid in ('FACE_PV.S0','FACE_PV.S1'))
settings.slot_selection_json=encode_targets(records)
slot_tools.activate_selection(scene,project)
assert len(slot_tools.target_specs(scene,project))==2
assert len(project.associations)==1
assert hasattr(bpy.ops.aludiy,'unlink_slots')
assert hasattr(bpy.types,'ALUDIY_OT_edit_joint_options')
from bl_ext.aludiy_upgrade.aludiy_designer import joint_editor
assert joint_editor._ACTIVE is None
empty = bpy.data.scenes.new('FreshEmptyAfterUpgrade')
assert runtime.settings(empty).project_json == ''
assert not runtime.get_project(empty).members
assert runtime.settings(empty).project_json == ''
print('UPGRADE_WITHOUT_UNINSTALL_OK')
''')
text=run('new-reopen',['-b',str(out/'old.blend'),'--python-exit-code','1','--python',str(check)])
assert 'UPGRADE_WITHOUT_UNINSTALL_OK' in text
print('UPGRADE_WITHOUT_UNINSTALL_OK')
