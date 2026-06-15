from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STORAGE_ROOT = PROJECT_ROOT / "storage"


def ensure_storage_dirs() -> None:
    for name in ("uploads", "jobs", "results", "charts", "reports", "logs"):
        (STORAGE_ROOT / name).mkdir(parents=True, exist_ok=True)
