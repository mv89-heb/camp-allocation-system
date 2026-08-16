from __future__ import annotations

import os


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"FATAL: required environment variable {name} is missing")
    return value


# Current operational phase: authentication is disabled.
# Remove legacy auth secrets from the process before app.main is imported,
# so an old Render environment variable cannot accidentally re-enable login.
os.environ.pop("ADMIN_TOKEN", None)
os.environ.pop("FIELD_TOKEN", None)

if os.getenv("RENDER", "").strip().lower() == "true" or os.getenv("DATABASE_URL", "").strip():
    _require("DATABASE_URL")

import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.entrypoint:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
