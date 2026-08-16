from __future__ import annotations

import os


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"FATAL: required environment variable {name} is missing")
    return value


# For the current phase only the Neon database connection is mandatory.
# Authentication is intentionally deferred; the field workflow must be usable
# without ADMIN_TOKEN/FIELD_TOKEN configuration.
if os.getenv("RENDER", "").strip().lower() == "true" or os.getenv("DATABASE_URL", "").strip():
    _require("DATABASE_URL")

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.entrypoint:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
