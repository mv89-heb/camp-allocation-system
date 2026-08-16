from __future__ import annotations

import os
import sys


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"FATAL: required production environment variable {name} is missing", file=sys.stderr)
        raise SystemExit(1)
    return value


# Render production must never start the application without both scopes.
if os.getenv("RENDER", "").strip().lower() == "true" or os.getenv("DATABASE_URL", "").strip():
    _require("DATABASE_URL")
    _require("ADMIN_TOKEN")
    _require("FIELD_TOKEN")

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.entrypoint:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
