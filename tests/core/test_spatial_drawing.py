from __future__ import annotations

import pytest

from aludiy_core.drawing import (
    closest_point_on_axis_to_ray,
    point_on_workplane_from_ray,
    polar_endpoint_mm,
)
from aludiy_core.errors import GeometryError


def test_xy_workplane_uses_explicit_offset_for_first_point() -> None:
    point = point_on_workplane_from_ray(
        ray_origin_mm=(125.0, 250.0, 1000.0),
        ray_direction=(0.0, 0.0, -1.0),
        work_plane="XY",
        offset_mm=300.0,
    )

    assert point == pytest.approx((125.0, 250.0, 300.0))


def test_workplane_passes_through_current_start_for_continuous_spatial_drawing() -> None:
    point = point_on_workplane_from_ray(
        ray_origin_mm=(200.0, 400.0, 1500.0),
        ray_direction=(0.0, 0.0, -1.0),
        work_plane="XY",
        offset_mm=0.0,
        start_mm=(50.0, 60.0, 800.0),
    )

    assert point == pytest.approx((200.0, 400.0, 800.0))


@pytest.mark.parametrize(
    ("plane", "origin", "direction", "offset", "expected"),
    [
        ("XZ", (100.0, 1000.0, 200.0), (0.0, -1.0, 0.0), 75.0, (100.0, 75.0, 200.0)),
        ("YZ", (1000.0, 120.0, 240.0), (-1.0, 0.0, 0.0), 50.0, (50.0, 120.0, 240.0)),
    ],
)
def test_vertical_workplanes_support_side_plane_drawing(
    plane, origin, direction, offset, expected
) -> None:
    point = point_on_workplane_from_ray(
        ray_origin_mm=origin,
        ray_direction=direction,
        work_plane=plane,
        offset_mm=offset,
    )

    assert point == pytest.approx(expected)


def test_polar_input_maps_angle_into_selected_workplane() -> None:
    start = (100.0, 200.0, 300.0)

    assert polar_endpoint_mm(start, "XY", 500.0, 90.0) == pytest.approx(
        (100.0, 700.0, 300.0)
    )
    assert polar_endpoint_mm(start, "XZ", 500.0, 90.0) == pytest.approx(
        (100.0, 200.0, 800.0)
    )
    assert polar_endpoint_mm(start, "YZ", 500.0, 90.0) == pytest.approx(
        (100.0, 200.0, 800.0)
    )


def test_world_z_axis_lock_projects_mouse_ray_to_vertical_member() -> None:
    point = closest_point_on_axis_to_ray(
        axis_origin_mm=(0.0, 0.0, 0.0),
        axis="Z",
        ray_origin_mm=(1000.0, 0.0, 650.0),
        ray_direction=(-1.0, 0.0, 0.0),
    )

    assert point == pytest.approx((0.0, 0.0, 650.0))


def test_axis_lock_rejects_view_ray_parallel_to_axis() -> None:
    with pytest.raises(GeometryError, match="parallel"):
        closest_point_on_axis_to_ray(
            axis_origin_mm=(0.0, 0.0, 0.0),
            axis="Z",
            ray_origin_mm=(100.0, 0.0, 0.0),
            ray_direction=(0.0, 0.0, 1.0),
        )


def test_axis_lock_only_accepts_nodes_on_locked_axis_within_tolerance() -> None:
    from aludiy_core.drawing import point_is_on_axis

    assert point_is_on_axis(
        (0.0, 0.0, 800.0),
        axis_origin_mm=(0.0, 0.0, 0.0),
        axis="Z",
        tolerance_mm=0.1,
    )
    assert not point_is_on_axis(
        (10.0, 0.0, 800.0),
        axis_origin_mm=(0.0, 0.0, 0.0),
        axis="Z",
        tolerance_mm=5.0,
    )
