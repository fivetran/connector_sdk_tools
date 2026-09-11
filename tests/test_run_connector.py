"""Run a fake SDK with a tester child; no network or real connector required."""

import os
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock


HELPER = Path(__file__).resolve().parents[1] / "canonical/tools/run_connector.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("run_fixture", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


class LifecycleTests(unittest.TestCase):
    def test_child_exit_124_is_not_a_timeout(self):
        helper = load_helper()
        self.assertEqual(helper.run_debug(
            [sys.executable, "-c", "raise SystemExit(124)"], Path.cwd(), 5), 124)

    def test_child_exit_124_still_reports_pipe_error(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / 'configuration.json').write_text('{}')
            pipe = Mock()
            pipe.__enter__ = Mock(return_value='unused')
            pipe.__exit__ = Mock(return_value=False)
            pipe.writer_error = OSError('fixture pipe failure')
            output = io.StringIO()
            with patch.object(sys, 'argv', [str(HELPER), tmp]), \
                 patch.object(helper, 'ConfigPipe', return_value=pipe), \
                 patch.object(helper, 'run_debug', return_value=124), \
                 contextlib.redirect_stderr(output):
                with self.assertRaises(SystemExit) as error:
                    helper.main()
            self.assertEqual(error.exception.code, 1)
            self.assertIn('fixture pipe failure', output.getvalue())

    def test_windows_cleanup_failures_are_reported(self):
        import ctypes
        for failure in ('open', 'cancel', 'deadline'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                helper = load_helper()
                pipe = helper.ConfigPipe(Path(tmp), {})
                pipe.writer_thread = Mock()
                pipe.writer_thread.is_alive.return_value = True
                pipe.writer_thread.native_id = 123
                kernel = Mock()
                kernel.OpenThread.return_value = 0 if failure == 'open' else 1
                kernel.CancelSynchronousIo.return_value = failure != 'cancel'
                output = io.StringIO()
                with patch.object(helper.os, 'name', 'nt'), \
                     patch.object(ctypes, 'WinDLL', return_value=kernel, create=True), \
                     patch.object(ctypes, 'get_last_error', return_value=5, create=True), \
                     patch.object(helper.time, 'monotonic', side_effect=[0, 0, 2]), \
                     contextlib.redirect_stderr(output):
                    pipe.__exit__(None, None, None)
                self.assertIn('pipe may remain open', output.getvalue())
                if failure == 'open':
                    self.assertIn('OpenThread failed', output.getvalue())
                elif failure == 'cancel':
                    self.assertIn('CancelSynchronousIo failed', output.getvalue())
                else:
                    self.assertIn('cleanup deadline', output.getvalue())

    def test_exception_stops_process_tree(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "heartbeat"
            worker = (
                "import pathlib, time; "
                "p = pathlib.Path('heartbeat'); p.write_text('started'); "
                "print('ready', flush=True); "
                "exec(\"while True:\\n p.write_text(str(time.time_ns())); time.sleep(0.02)\")"
            )
            with patch("builtins.print", side_effect=RuntimeError("output failed")):
                with self.assertRaisesRegex(RuntimeError, "output failed"):
                    helper.run_debug([sys.executable, "-c", worker], Path(tmp), 5)
            value = heartbeat.read_text()
            time.sleep(0.1)
            self.assertEqual(heartbeat.read_text(), value)

    def test_unused_config_pipe_cancels_writer_promptly(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            pipe = helper.ConfigPipe(Path(tmp), {"setting": "value"})
            start = time.monotonic()
            with pipe:
                pass
            self.assertLess(time.monotonic() - start, 3)
            self.assertFalse(pipe.writer_thread.is_alive())

    @unittest.skipUnless(os.name == "nt", "Requires native Windows Job Objects")
    def test_windows_job_stops_tester_after_parent_exits(self):
        # Run the wrapper in a separate process so a broken job implementation
        # fails with a bounded timeout instead of hanging the test suite.
        with tempfile.TemporaryDirectory() as tmp:
            child = "import time; print('tester ready', flush=True); time.sleep(60)"
            parent = f"import subprocess,sys; subprocess.Popen([sys.executable, '-c', {child!r}])"
            driver = (
                "import runpy,sys,subprocess; from pathlib import Path; "
                f"h = runpy.run_path({str(HELPER)!r}); "
                "\ntry:\n"
                f" sys.exit(h['run_debug']([sys.executable, '-c', {parent!r}], Path('.'), 1))\n"
                "except subprocess.TimeoutExpired:\n sys.exit(124)\n"
            )
            result = subprocess.run([sys.executable, "-c", driver], cwd=tmp,
                                    capture_output=True, text=True, timeout=8)
            self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
            self.assertIn("tester ready", result.stdout)


class ConfigurationTests(unittest.TestCase):
    def test_both_loaders_reject_non_string_values_without_exposing_them(self):
        for filename in ('run_connector.py', 'deploy_connector.py'):
            spec = importlib.util.spec_from_file_location('config_fixture', HELPER.with_name(filename))
            helper = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(helper)
            with tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / 'configuration.json'
                for value in ({'secret': 'private-value'}, ['private-value'], 42, True, None):
                    with self.subTest(helper=filename, value=value):
                        config.write_text(json.dumps({'setting': value}))
                        with self.assertRaisesRegex(ValueError, 'must be a string') as error:
                            helper.load_runtime_config(config)
                        self.assertNotIn('private-value', str(error.exception))
                config.write_text('{"setting":"42","empty":""}')
                self.assertEqual(helper.load_runtime_config(config), {'setting': '42', 'empty': ''})


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
                + ("time.sleep(60)\n" if mode == "unopened_pipe" else "")
                + "with open(sys.argv[sys.argv.index('--configuration') + 1]) as stream:\n"
                "    assert json.load(stream) == {'setting': 'value'}\n"
                + ("print('debug completed', flush=True)\n" if mode == "success" else
                   f"subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
                   "print('tester started', flush=True)\n"
                   + ("time.sleep(60)\n" if mode in ("running_parent", "interrupt", "terminate") else ""))
            )
            executable.chmod(0o700)
            try:
                cmd = [sys.executable, str(HELPER), str(project), "--timeout-seconds",
                       "60" if mode in ("interrupt", "terminate") else "1"]
                if mode in ("interrupt", "terminate"):
                    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True) as wrapper:
                        try:
                            deadline = time.monotonic() + 5
                            while not (project / "heartbeat").exists():
                                if time.monotonic() > deadline:
                                    self.fail("tester did not start")
                                time.sleep(0.02)
                            signum = signal.SIGINT if mode == "interrupt" else signal.SIGTERM
                            wrapper.send_signal(signum)
                            stdout, stderr = wrapper.communicate(timeout=5)
                            result = subprocess.CompletedProcess(cmd, wrapper.returncode, stdout, stderr)
                        finally:
                            if wrapper.poll() is None:
                                wrapper.kill()
                else:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                if mode == "success":
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("debug completed", result.stdout)
                    self.assertNotIn("timed out", result.stdout)
                elif mode == "unopened_pipe":
                    self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
                else:
                    expected = 130 if mode == "interrupt" else 143 if mode == "terminate" else 124
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    self.assertIn("tester started", result.stdout)
                    if expected == 124:
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

    def test_timeout_before_sdk_opens_config_pipe(self):
        self.run_fixture("unopened_pipe")

    def test_ctrl_c_stops_sdk_and_tester(self):
        self.run_fixture("interrupt")

    def test_sigterm_stops_sdk_and_tester(self):
        self.run_fixture("terminate")


if __name__ == "__main__":
    unittest.main()
