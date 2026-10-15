from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[2]
EXTENSION = ROOT / "extension" / "aludiy_designer"


def test_optional_service_failure_is_returned_instead_of_raised() -> None:
    from aludiy_core.startup import try_optional_service

    def broken() -> None:
        raise RuntimeError("GPU callback unavailable")

    error = try_optional_service("viewport overlay", broken)

    assert error == "viewport overlay：GPU callback unavailable"


def test_optional_service_success_returns_no_error() -> None:
    from aludiy_core.startup import try_optional_service

    called: list[bool] = []

    error = try_optional_service("view sync", lambda: called.append(True))

    assert error is None
    assert called == [True]


def test_entry_point_does_not_import_gpu_overlay_at_module_import_time() -> None:
    tree = ast.parse((EXTENSION / "__init__.py").read_text(encoding="utf-8"))
    imported_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)

    assert "viewport_overlay" not in imported_names


def test_entry_point_registers_core_before_optional_services() -> None:
    tree = ast.parse((EXTENSION / "__init__.py").read_text(encoding="utf-8"))
    register = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "register"
    )
    statement_calls: list[set[str]] = []
    for statement in register.body:
        names: set[str] = set()
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                names.add(node.func.id)
        statement_calls.append(names)

    core_index = next(i for i, names in enumerate(statement_calls) if "register_class" in names)
    optional_index = next(
        i for i, names in enumerate(statement_calls) if "_register_optional_services" in names
    )
    assert core_index < optional_index
