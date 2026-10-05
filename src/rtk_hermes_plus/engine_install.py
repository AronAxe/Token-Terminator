"""Install the user adapter; explicit CLI installation also repairs the known host loader."""

from __future__ import annotations

import json
import os
from importlib.resources import files as package_files
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


def install_context_engine(
    home: Path | None = None, *, repair_discovery: bool = False
) -> dict:
    home = Path(home) if home is not None else _hermes_home()
    destination = home / "plugins" / "token-terminator"
    files = {
        "__init__.py": _SHIM,
        "plugin.yaml": f"# Token Terminator managed ContextEngine adapter\nname: token-terminator\nversion: '{__version__}'\ndescription: 'Token Terminator â€” exact-history ContextEngine and request middleware'\n",
    }
    files.update(
        {
            "dashboard/plugin_api.py": _MARKER
            + "\nfrom rtk_hermes_plus.dashboard_api import router  # noqa: F401\n",
            "dashboard/manifest.json": json.dumps(
                {
                    "name": "token-terminator",
                    "api": "plugin_api.py",
                    "entry": "noop.js",
                    "tab": {"hidden": True},
                    "_managed_by": "token-terminator",
                    "description": "Read-only TT accounting",
                },
                indent=2,
            )
            + "\n",
            "dashboard/noop.js": "// Token Terminator managed Desktop dashboard adapter\n// Backend-only web-dashboard entry; native Desktop contributes its own UI.\n",
            "desktop/plugin.js": package_files("rtk_hermes_plus")
            .joinpath("dashboard_assets", "plugin.js")
            .read_text(encoding="utf-8"),
        }
    )
    for parent in (
        home,
        *home.parents,
        home / "plugins",
        destination,
        destination / "dashboard",
        destination / "desktop",
    ):
        if parent.is_symlink():
            raise ValueError("refusing a symlinked plugin destination")
    for name in files:
        path = destination / name
        managed = True
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if name.endswith("manifest.json"):
                try:
                    managed = json.loads(text).get("_managed_by") == "token-terminator"
                except (ValueError, AttributeError):
                    managed = False
            else:
                marker = (
                    "// Token Terminator managed Desktop dashboard adapter"
                    if name.endswith(".js")
                    else _MARKER
                )
                managed = text.startswith(marker)
        if path.is_symlink() or not managed:
            raise ValueError("refusing to replace an unmanaged plugin file")
    # This host bug happens before plugin code can run. Repair only the reviewed
    # affected loader, only during an explicit install, with a recoverable backup.
    from .hermes_discovery import repair_hermes_discovery

    discovery = (
        repair_hermes_discovery()
        if repair_discovery
        else {"state": "not_requested", "changed": False}
    )
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = destination / name
        # Atomic replacement inside a user-owned directory. No credentials stored.
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.parent / (path.name + ".tt-new")
        with temp.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp, path)
    return {
        "installed": str(destination),
        "version": __version__,
        "config_changed": False,
        "discovery_repair": discovery,
        "next_steps": [
            "Enable token-terminator in hermes plugins (general plugin/middleware).",
            "Choose token-terminator under Provider Plugins > Context Engine.",
            "Restart the Hermes process; verify token_terminator_history action=status.",
            "Enable Token Terminator's Desktop half in Capabilities > Plugins for the status-bar counter.",
            "Run token-terminator dashboard for the localhost:7474 dashboard.",
        ],
    }
