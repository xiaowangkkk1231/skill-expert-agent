import os
import pathlib
import tempfile

_tmp = pathlib.Path(tempfile.mkdtemp(prefix="sea-test-")) / "test.db"
os.environ["SEA_DB_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["SEA_PROVIDER"] = "rule"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import init_db  # noqa: E402

init_db()
