"""RTK Hermes Plus plugin entrypoint."""

from ._version import __version__
from .plugin import Runtime, register

__all__ = ["Runtime", "__version__", "register"]
