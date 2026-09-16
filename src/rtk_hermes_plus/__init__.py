"""Token Terminator plugin entrypoint.

The historical ``rtk_hermes_plus`` import path remains stable for source and
installed-package compatibility while the public distribution and plugin are
named Token Terminator.
"""

from . import plugin as _plugin
from ._version import __version__
from .cancellation import CancellationToken
from .enhancements import install as install_v05
from .v06 import RuntimeV06, install as install_v06

install_v05(_plugin)
install_v06(_plugin)
Runtime = RuntimeV06
register = _plugin.register

# Import the async facade only after the enhanced runtime has been installed so
# its Runtime annotation and downstream users see the active implementation.
from .async_runtime import AsyncRuntime

__all__ = [
    "AsyncRuntime",
    "CancellationToken",
    "Runtime",
    "__version__",
    "register",
]
