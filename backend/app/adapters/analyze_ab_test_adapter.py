import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path.home() / ".codex" / "skills" / "ab-test-significance-evaluator" / "scripts" / "analyze_ab_test.py"


def run_stage2_script(input_path: Path, output_path: Path, sheet_name: str) -> subprocess.CompletedProcess[str]:
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Stage 2 script not found: {SCRIPT_PATH}")
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        str(input_path),
        "--output",
        str(output_path),
        "--sheet",
        sheet_name,
    ]
    return subprocess.run(command, capture_output=True, text=True, check=False)
