"""Ephemeral browser-test server; never opens the configured development database."""

import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
with tempfile.TemporaryDirectory(prefix="who-could-browser-") as directory:
    os.environ.update(
        WHO_COULD_ENV="test",
        WHO_COULD_SECRET="browser-tests-only-secret-32-characters",
        DATABASE_URL="sqlite:///" + directory + "/browser.db",
        UPLOAD_DIR=directory + "/uploads",
        PUBLIC_URL="http://127.0.0.1:5173",
        BILLING_ENFORCED="false",
    )
    from alembic import command
    from alembic.config import Config
    import uvicorn

    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
