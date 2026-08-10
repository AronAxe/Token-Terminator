"""RTK Hermes Plus plugin entrypoint."""

from .plugin import Runtime, register

__all__ = ["Runtime", "register"]
__version__ = "0.1.0"
