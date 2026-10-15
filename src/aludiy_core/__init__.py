"""Public API for the Blender-independent AluDIY engineering core."""

from .catalog import ProfileCatalog, compile_catalog
from .errors import (
    AluDIYError,
    CatalogError,
    GeometryError,
    InputParseError,
    DuplicateIdError,
    MissingReferenceError,
    ValidationError,
)
from .model import (
    FaceDefinition,
    InterfaceDefinition,
    Member,
    MemberRemovalResult,
    Node,
    ProfileType,
    Project,
    SectionDefinition,
)

__all__ = [
    "AluDIYError",
    "CatalogError",
    "DuplicateIdError",
    "GeometryError",
    "InputParseError",
    "FaceDefinition",
    "InterfaceDefinition",
    "Member",
    "MemberRemovalResult",
    "MissingReferenceError",
    "Node",
    "ProfileCatalog",
    "ProfileType",
    "Project",
    "SectionDefinition",
    "ValidationError",
    "compile_catalog",
]

from .geometry import (
    MemberEnvelope,
    MemberMesh,
    derive_member_envelope,
    derive_member_mesh,
    member_length_mm,
    resize_member,
    section_outline_uv,
)
from .units import PolarInput, parse_distance_mm, parse_length_mm, parse_polar

__all__ += [
    "MemberEnvelope", "MemberMesh", "PolarInput", "derive_member_envelope",
    "derive_member_mesh", "member_length_mm", "parse_length_mm", "parse_polar",
    "resize_member", "section_outline_uv"
]

from .cutlist import CutListRow, cutlist_rows, write_cutlist_csv
from .io import catalog_revision_warning, create_sample_frame, load_project, save_project

__all__ += [
    "CutListRow",
    "catalog_revision_warning",
    "create_sample_frame",
    "cutlist_rows",
    "load_project",
    "save_project",
    "write_cutlist_csv",
    "try_optional_service",
]

from .startup import try_optional_service
