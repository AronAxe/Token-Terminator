"""Hermes-authenticated, current-profile-only read API for the Desktop widget.

Hermes supplies FastAPI and binds get_hermes_home through its existing plugin
route dependency. Importing this module never starts a server, Runtime or model.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import replace

from fastapi import APIRouter, HTTPException, Response

from .config import _hermes_home
from .dashboard_data import configuration, snapshot

router = APIRouter()
_lock = threading.Lock()
_cache = OrderedDict()


def _current_snapshot():
    # This is the already authorized request's home, not a client-supplied path.
    home = _hermes_home().expanduser().absolute()
    try:
        from hermes_cli.profiles import current_profile_name

        name = current_profile_name() or "default"
    except ImportError:
        name = home.name if home.parent.name == "profiles" else "default"
    key = (str(home), name)
    with _lock:
        existing = _cache.get(key)
        if existing and time.monotonic() - existing[0] < 5:
            _cache.move_to_end(key)
            return existing[1]
        sources, rates = configuration(home, discover=False)
        # A multi-profile standalone dashboard can have an aggregate source list;
        # the authenticated Desktop API must never enumerate other profile homes.
        selected = [s for s in sources if s.id == name]
        if not selected and len(sources) == 1 and sources[0].id == "default":
            selected = sources  # custom standalone HERMES_HOME, explicitly labelled
        if len(selected) != 1:
            raise ValueError("no unambiguous current-profile source")
        source = replace(selected[0], expected_profile=name)
        for path in (source.vault, source.ledger):
            path.resolve().relative_to(
                home.resolve()
            )  # external stores: standalone only
        data = snapshot([source], rates)
        data["scope"] = {"profile": name, "current_profile_only": True}
        _cache[key] = (time.monotonic(), data)
        while len(_cache) > 16:
            _cache.popitem(last=False)
        return data


@router.get("/summary")
def summary(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    try:
        return _current_snapshot()
    except Exception:  # noqa: BLE001 - no paths, source data or SQL in errors
        raise HTTPException(
            status_code=503, detail="TT accounting unavailable"
        ) from None
