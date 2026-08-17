"""Token Terminator plugin entrypoint.

The historical ``rtk_hermes_plus`` import path remains stable for source and
installed-package compatibility while the public distribution and plugin are
named Token Terminator.
"""

from ._version import __version__
from .plugin import Runtime, register

__all__ = ["Runtime", "__version__", "register"]
