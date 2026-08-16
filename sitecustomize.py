"""Render startup safety hook.

Python imports ``sitecustomize`` automatically when it is on sys.path.  This hook
makes the production data reconciliation independent of Render's dashboard
Start Command: when the process being started is Uvicorn and DATABASE_URL is
configured, the repository snapshot is reconciled into Neon before the ASGI
server is imported.

It is deliberately limited to Uvicorn so that pip/build/test commands do not
attempt to connect to the production database.
"""
from __future__ import annotations

import os
import sys


def _is_uvicorn_process() -> bool:
    argv = " ".join(sys.argv[:4]).lower()
    return "uvicorn" in argv


if _is_uvicorn_process() and os.getenv("DATABASE_URL", "").strip():
    try:
        from bootstrap_neon import main as bootstrap_main

        bootstrap_main()
    except Exception:
        # A production server must not silently start against an unsynchronised
        # database.  The exception is intentionally re-raised so Render marks
        # the deployment unhealthy and exposes the real startup failure in logs.
        raise
