from aludiy_core import Project,Member,Node
from aludiy_core import snapping

def test_member_axis_candidates_include_midpoint_and_interior():
    assert hasattr(snapping,'member_candidates'),'body snapping missing'
    p=Project('P','R');p.add_node(Node('N1',(0,0,0)));p.add_node(Node('N2',(1000,0,0)));p.add_member(Member('M','N1','N2','P'))
    def project(x): return x[:2]
    for station in (250,500,750):
        cs=snapping.member_candidates(p,origin_mm=(0,100,0),cursor_px=(station,1),project_point=project,
            ray_origin_mm=(station,1,100),ray_direction=(0,0,-1),radius_px=14)
        assert cs and cs[0].member_id=='M'
        assert abs(cs[0].position_mm[0]-station)<1e-8 and cs[0].position_mm[1]==0
        assert cs[0].node_id is None
    assert not snapping.member_candidates(p,origin_mm=(250,100,0),cursor_px=(300,0),project_point=project,
            ray_origin_mm=(300,0,100),ray_direction=(0,0,-1),axis='Z',radius_px=14)
