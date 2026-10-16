"""Selection identity across managed display-cache rebuilds; no stale RNA refs."""
from . import runtime


def capture(context):
    def key(obj):
        if obj is None:
            return None
        eid = runtime.entity_id_from_object(obj) if obj.get('aludiy_managed') else None
        return ('ENGINEERING', eid, obj.get('aludiy_entity_type')) if eid else ('OBJECT', obj.name, '')
    return ([key(o) for o in context.view_layer.objects if o.select_get()],
            key(context.view_layer.objects.active))


def restore(context, snapshot):
    selected, active = snapshot
    ids = {item[1] for item in selected if item[0] == 'ENGINEERING'}
    names = {item[1] for item in selected if item[0] == 'OBJECT'}
    preferred = fallback = None
    for obj in context.view_layer.objects:
        eid = runtime.entity_id_from_object(obj) if obj.get('aludiy_managed') else None
        wanted = eid in ids if eid else obj.name in names
        if obj.select_get() != wanted:
            obj.select_set(wanted)
        if active:
            match = eid == active[1] if active[0] == 'ENGINEERING' else obj.name == active[1]
            if match:
                fallback = obj
                if active[0] == 'OBJECT' or obj.get('aludiy_entity_type') == active[2]:
                    preferred = obj
    context.view_layer.objects.active = preferred or fallback
    from . import view_sync
    view_sync._LAST_SELECTED_BY_WINDOW.clear()
    view_sync._LAST_ENTITY_BY_WINDOW.clear()
