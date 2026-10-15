from __future__ import annotations

import pytest

from aludiy_core.errors import InputParseError
from aludiy_core.units import parse_length_mm, parse_polar


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1200", 1200.0),
        ("1200mm", 1200.0),
        ("120cm", 1200.0),
        ("1.2m", 1200.0),
        ("600+20", 620.0),
        ("(1m + 20cm) / 2", 600.0),
    ],
)
def test_parse_length_mm_supports_units_and_safe_arithmetic(
    text: str, expected: float
) -> None:
    assert parse_length_mm(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('echo unsafe')",
        "sin(30)",
        "1/0",
        "nan",
        "2**10",
        "-1mm",
        "0",
    ],
)
def test_parse_length_mm_rejects_unsafe_or_non_positive_input(text: str) -> None:
    with pytest.raises(InputParseError):
        parse_length_mm(text)


def test_parse_polar_returns_exact_length_and_angle() -> None:
    polar = parse_polar("@1.2m<30")

    assert polar.length_mm == pytest.approx(1200.0)
    assert polar.angle_deg == pytest.approx(30.0)


def test_parse_distance_mm_allows_zero_and_signed_workplane_offsets() -> None:
    from aludiy_core.units import parse_distance_mm

    assert parse_distance_mm("0") == pytest.approx(0.0)
    assert parse_distance_mm("-0.8m") == pytest.approx(-800.0)
    assert parse_distance_mm("600-20") == pytest.approx(580.0)
