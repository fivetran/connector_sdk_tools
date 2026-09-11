"""Run a fake SDK with a tester child; no network or real connector required."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


HELPER = Path(__file__).resolve().parents[1] / "canonical/tools/run_connector.py"


@unittest.skipUnless(os.name == "posix", "Fake SDK executable uses a POSIX shebang")
class RunTests(unittest.TestCase):
    def run_fixture(self, mode):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "configuration.json").write_text('{"setting": "value"}')
            executable = project / ".venv/bin/fivetran"
            executable.parent.mkdir(parents=True)
            child_code = (
                "import pathlib, time\n"
                "while True:\n"
                "    pathlib.Path('heartbeat').write_text(str(time.time_ns()))\n"
                "    time.sleep(0.02)\n"
            )
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json, os, pathlib, subprocess, sys, time\n"
                "pathlib.Path('sdk_pid').write_text(str(os.getpid()))\n"
                "with open(sys.argv[sys.argv.index('--configuration') + 1]) as stream:\n"
                "    assert json.load(stream) == {'setting': 'value'}\n"
                + ("print('debug completed', flush=True)\n" if mode == "success" else
                   f"subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
                   "print('tester started', flush=True)\n"
                   + ("time.sleep(60)\n" if mode == "running_parent" else ""))
            )
            executable.chmod(0o700)
            try:
                result = subprocess.run(
                    [sys.executable, str(HELPER), str(project), "--timeout-seconds", "1"],
                    capture_output=True, text=True, timeout=8,
                )
                if mode == "success":
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("debug completed", result.stdout)
                    self.assertNotIn("timed out", result.stdout)
                else:
                    self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
                    self.assertIn("tester started", result.stdout)
                    self.assertIn("timed out after 1 seconds", result.stdout)
                    # The child inherited stdout. Returning promptly proves that
                    # handle closed; a stopped heartbeat also checks it stopped work.
                    heartbeat = (project / "heartbeat").read_text()
                    time.sleep(0.1)
                    self.assertEqual((project / "heartbeat").read_text(), heartbeat)
                self.assertFalse(list(project.glob(".config_pipe*")))
            finally:
                # Clean up even when testing an implementation that leaks children.
                pid_file = project / "sdk_pid"
                if pid_file.exists():
                    try:
                        os.killpg(int(pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_timeout_kills_tester_and_sdk(self):
        self.run_fixture("running_parent")

    def test_timeout_kills_tester_after_sdk_exits(self):
        self.run_fixture("exited_parent")

    def test_success_keeps_normal_exit_status(self):
        self.run_fixture("success")


if __name__ == "__main__":
    unittest.main()
