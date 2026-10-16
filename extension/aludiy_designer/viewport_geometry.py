"""The single float64 millimetre boundary for all viewport snapping tools."""
from bpy_extras import view3d_utils
from mathutils import Vector


def world_ray_mm(region, region_3d, cursor_px):
    # Do not multiply a Blender Vector by 1000: that rounds to float32 again.
    origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, cursor_px)
    direction = view3d_utils.region_2d_to_vector_3d(region, region_3d, cursor_px)
    return tuple(float(v)*1000.0 for v in origin), tuple(float(v) for v in direction)


def project_point_mm(region, region_3d, position_mm):
    # Values entering Blender are for display only; the authoritative position
    # stays an unchanged Python tuple of doubles in the engineering core.
    point = view3d_utils.location_3d_to_region_2d(
        region, region_3d, Vector(tuple(float(v)*0.001 for v in position_mm)), default=None)
    return tuple(point) if point is not None else None
