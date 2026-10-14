import os
import tempfile
from pathlib import Path


TEST_ROOT = Path(tempfile.mkdtemp(prefix="dq-lineage-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'quality-test.db'}"
os.environ["STORAGE_PATH"] = str(TEST_ROOT / "datasets")
os.environ.pop("OPENAI_API_KEY", None)

