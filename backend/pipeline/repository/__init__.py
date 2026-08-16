"""Query layer. One module per table; each takes a connection as its first argument."""

from . import companies

__all__ = ["companies"]
