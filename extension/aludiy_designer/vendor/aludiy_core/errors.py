"""Domain errors raised by the AluDIY engineering core."""


class AluDIYError(Exception):
    """Base class for all predictable AluDIY errors."""


class ValidationError(AluDIYError):
    """Raised when structured engineering data is invalid."""


class DuplicateIdError(ValidationError):
    """Raised when a stable entity identifier is repeated."""


class MissingReferenceError(ValidationError):
    """Raised when an entity points at an unknown stable identifier."""


class CatalogError(AluDIYError):
    """Raised when profile catalog source or compiled data is invalid."""


class InputParseError(AluDIYError):
    """Raised when precise numeric input cannot be parsed safely."""


class GeometryError(ValidationError):
    """Raised when valid engineering geometry cannot be derived."""
