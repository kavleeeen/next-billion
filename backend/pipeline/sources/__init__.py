"""Source connectors. Each exposes NAME, parse(payloads) and fetch()."""

from . import hackernews, yc

__all__ = ["hackernews", "yc"]
