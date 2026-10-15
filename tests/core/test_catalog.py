from __future__ import annotations

from pathlib import Path

from aludiy_core.catalog import ProfileCatalog, compile_catalog


CATALOG_SOURCE = Path(__file__).parents[2] / "catalog" / "profiles"


def test_source_catalog_contains_five_alpha_profiles() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)

    assert set(catalog.profile_ids()) == {
        "generic:tslot-2020@0.1",
        "generic:tslot-2040@0.1",
        "generic:tslot-3030-3open@0.1",
        "generic:tslot-3030@0.1",
        "generic:tslot-3060@0.1",
    }


def test_2040_profile_exposes_six_stable_slot_interfaces() -> None:
    catalog = ProfileCatalog.from_source_directory(CATALOG_SOURCE)
    profile = catalog.get("generic:tslot-2040@0.1")

    assert profile.section.width_mm == 40.0
    assert profile.section.height_mm == 20.0
    assert len(profile.section.interfaces) == 6
    assert set(profile.section.faces["FACE_PV"].interface_ids) == {
        "FACE_PV.S0",
        "FACE_PV.S1",
    }
    assert profile.section.interfaces["FACE_PV.S1"].lane_index == 1
    assert profile.section.interfaces["FACE_PV.S1"].lane_count == 2


def test_compiled_sqlite_catalog_round_trips_profile_payloads(tmp_path: Path) -> None:
    database = tmp_path / "profile_catalog.sqlite"
    compile_catalog(CATALOG_SOURCE, database)

    catalog = ProfileCatalog.from_sqlite(database)

    assert len(catalog) == 5
    assert catalog.get("generic:tslot-3030-3open@0.1").section.faces[
        "FACE_NV"
    ].interface_ids == ()
