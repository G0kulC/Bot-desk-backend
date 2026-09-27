"""Start the API server. Run with: python run.py  (or: uv run python run.py)

Optional env vars: HOST (default 0.0.0.0), PORT (default 8000), RELOAD (default on when APP_ENV=dev).
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

# Settings read .env from the working directory, so always run from the backend folder.
os.chdir(Path(__file__).resolve().parent)

from app.config import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings()
    reload_default = "1" if settings.APP_ENV == "dev" else "0"
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", reload_default) == "1",
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
