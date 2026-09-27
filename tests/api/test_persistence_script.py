"""The out of process check, driven against a server this test starts, exactly as CI runs it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.postgres


def test_check_persistence_starts_a_server_and_reads_back_independently(clean_db: str) -> None:
    env = {**os.environ, "MARGINAL_TEST_DATABASE_URL": clean_db, "MARGINAL_WRITE_TOKEN": "check-token"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_persistence.py"), "--start-server", "--port", "8791"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "read back from outside the server process" in proc.stdout
    assert '"audit_before_response": true' in proc.stdout
