"""Install the supported user-directory adapter, without editing Hermes core/config."""

from __future__ import annotations

import os
from pathlib import Path

from ._version import __version__
from .config import _hermes_home

_MARKER = "# Token Terminator managed ContextEngine adapter"
_SHIM = """# Token Terminator managed ContextEngine adapter
from rtk_hermes_plus.hermes_engine import TokenTerminatorContextEngine


def register(ctx):
    # Directory ContextEngine discovery and general middleware discovery use
    # different documented registration contexts. One adapter supports both.
    if callable(getattr(ctx, "register_middleware", None)):
        from rtk_hermes_plus import register as register_middleware
        register_middleware(ctx)
    else:
        ctx.register_context_engine(TokenTerminatorContextEngine())
"""


def install_context_engine(home: Path | None = None) -> dict:
    home = Path(home) if home is not None else _hermes_home()
    destination = home / "plugins" / "token-terminator"
    files = {
        "__init__.py": _SHIM,
        "plugin.yaml": f"# Token Terminator managed ContextEngine adapter\nname: token-terminator\nversion: '{__version__}'\ndescription: 'Token Terminator — exact-history ContextEngine and request middleware'\n",
    }
    for parent in (home, home / "plugins", destination):
        if parent.is_symlink():
            raise ValueError("refusing a symlinked plugin destination")
    for name in files:
        path = destination / name
        if path.is_symlink() or (
            path.exists() and not path.read_text(encoding="utf-8").startswith(_MARKER)
        ):
            raise ValueError("refusing to replace an unmanaged plugin file")
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = destination / name
        # Atomic replacement inside a user-owned directory. No credentials stored.
        temp = destination / (name + ".tt-new")
        with temp.open("x", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp, path)
    return {
        "installed": str(destination),
        "version": __version__,
        "config_changed": False,
        "next_steps": [
            "Enable token-terminator in hermes plugins (general plugin/middleware).",
            "Choose token-terminator under Provider Plugins > Context Engine.",
            "Restart the Hermes process; verify token_terminator_history action=status.",
        ],
    }
