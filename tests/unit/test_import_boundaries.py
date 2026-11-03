import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_import_contracts_hold() -> None:
    result = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports"), "--no-cache"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
