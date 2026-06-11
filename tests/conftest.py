import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True


def pytest_configure():
    src_root = Path(__file__).resolve().parents[1] / "src"
    for path in src_root.rglob("*"):
        if path.name == "__pycache__":
            shutil.rmtree(path, ignore_errors=True)
        elif path.suffix == ".pyc":
            path.unlink(missing_ok=True)
