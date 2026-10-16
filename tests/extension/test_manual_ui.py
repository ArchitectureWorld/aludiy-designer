from pathlib import Path
E=Path(__file__).parents[2]/'extension/aludiy_designer'

def test_manual_buttons_and_full_selection_overlay():
    panel=(E/'panels.py').read_text(); g=(E/'g_move.py').read_text()
    for name in ('aludiy.create_associations','aludiy.remove_associations','吸附仅定位'):
        assert name in panel
    assert 'def selection_summary' in g
    assert 'def _draw_selection' in g
    assert 'delta_json' in g, 'float32 Operator properties must not round authoritative snap delta'

def test_draw_uses_independent_nodes_and_transaction():
    source=(E/'operators.py').read_text();method=source[source.index('    def _commit(self, context)'):source.index('    def modal(self, context, event)',source.index('    def _commit(self, context)'))]
    assert 'append_independent_member' in method
    assert '_commit_project_update' in method
