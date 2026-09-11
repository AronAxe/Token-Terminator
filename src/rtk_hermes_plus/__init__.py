"""Token Terminator plugin entrypoint.

The historical ``rtk_hermes_plus`` import path remains stable for source and
installed-package compatibility while the public distribution and plugin are
named Token Terminator.
"""

from . import plugin as _plugin
from ._version import __version__
from .cancellation import CancellationToken
from .enhancements import RuntimeV05, install

install(_plugin)
Runtime = RuntimeV05
register = _plugin.register

# Import the async facade only after the v0.5 runtime has been installed so its
# Runtime annotation and downstream users see the enhanced implementation.
from .async_runtime import AsyncRuntime  # noqa: E402

__all__ = [
    "AsyncRuntime",
    "CancellationToken",
    "Runtime",
    "__version__",
    "register",
]
