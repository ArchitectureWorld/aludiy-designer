"""Pure helpers for resilient host-application startup."""

from __future__ import annotations

from collections.abc import Callable


def try_optional_service(name: str, callback: Callable[[], None]) -> str | None:
    """Run an optional startup service and return a user-facing error on failure."""

    try:
        callback()
    except Exception as exc:  # Host APIs can vary by Blender build and context.
        return f"{name}：{exc}"
    return None
