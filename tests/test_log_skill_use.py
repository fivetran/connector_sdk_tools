"""Tests for canonical/hooks/log-skill-use.sh: opt-out, notice, events and bad input.

The hook runs as a subprocess with a stub `curl` first on PATH that records the
request body, so nothing touches the network.
"""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "canonical/hooks/log-skill-use.sh"
CURL_STUB = '#!/bin/bash\nwhile [[ $# -gt 0 ]]; do\n  [[ "$1" == "-d" ]] && printf \'%s\\n\' "$2" >> "$CURL_LOG"\n  shift\ndone\n'
PAYLOAD_KEYS = {"event", "plugin", "version", "skill", "status", "model", "session_id", "timestamp"}
POST_TOOL_USE = {"hook_event_name": "PostToolUse", "tool_name": "Skill",
                 "tool_input": {"skill": "fivetran-connector-sdk:build-connector"},
                 "model": "m", "session_id": "s"}


class HookHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        (self.bin / "curl").write_text(CURL_STUB)
        (self.bin / "curl").chmod(0o755)
        self.curl_log = tmp / "curl.log"
        self.manifest = tmp / "plugin.json"
        self.manifest.write_text(json.dumps({"name": "fivetran-connector-sdk", "version": "1.2.3"}))
        self.home = tmp / "home"
        self.home.mkdir()
        self.plugin_data = tmp / "plugin-data"

    def marker(self, host):
        """Where the one-time-notice marker lives for a host."""
        base = self.plugin_data if host == "claude-code" else self.home / ".fivetran/ai-plugins" / host
        return base / "telemetry-notice-shown"

    def mark_notice_shown(self, host="claude-code"):
        self.marker(host).parent.mkdir(parents=True, exist_ok=True)
        self.marker(host).touch()

    def run_hook(self, event, env=None, raw=None, host="claude-code", mark_shown=True):
        """Run the hook. By default the notice is treated as already shown, so events are sent."""
        if mark_shown:
            self.mark_notice_shown(host)
        full_env = {k: v for k, v in os.environ.items()
                    if k not in ("DO_NOT_TRACK", "FIVETRAN_TELEMETRY_DISABLED", "CLAUDE_PLUGIN_DATA")}
        full_env.update({"PATH": f"{self.bin}:{os.environ['PATH']}", "CURL_LOG": str(self.curl_log),
                         "HOME": str(self.home), "CLAUDE_PLUGIN_DATA": str(self.plugin_data)})
        full_env.update(env or {})
        data = raw if raw is not None else json.dumps(event)
        return subprocess.run(["bash", str(HOOK), str(self.manifest), host], input=data, text=True,
                              capture_output=True, env=full_env, timeout=15)

    def sent(self, expect=True):
        """Bodies recorded by the stub curl (it runs in the background, so poll)."""
        deadline = time.time() + (3 if expect else 0.7)
        while time.time() < deadline:
            if self.curl_log.exists() and self.curl_log.read_text().strip():
                break
            time.sleep(0.05)
        if not self.curl_log.exists():
            return []
        return [json.loads(line) for line in self.curl_log.read_text().splitlines() if line.strip()]


class OptOutTests(HookHarness):
    def test_sends_by_default(self):
        result = self.run_hook(POST_TOOL_USE)
        self.assertEqual(result.returncode, 0)
        [body] = self.sent()
        self.assertEqual(set(body), PAYLOAD_KEYS)
        self.assertEqual((body["skill"], body["status"]), ("build-connector", "ok"))

    def test_fivetran_telemetry_disabled(self):
        result = self.run_hook(POST_TOOL_USE, env={"FIVETRAN_TELEMETRY_DISABLED": "1"})
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual(self.sent(expect=False), [])

    def test_do_not_track_opts_out(self):
        for value in ("1", "true", "TRUE", " True ", "\t1\t"):
            with self.subTest(value=value):
                result = self.run_hook(POST_TOOL_USE, env={"DO_NOT_TRACK": value})
                self.assertEqual((result.returncode, result.stdout), (0, ""))
                self.assertEqual(self.sent(expect=False), [])

    def test_other_do_not_track_values_do_not_opt_out(self):
        for value in ("0", "false", "", "yes"):
            with self.subTest(value=value):
                self.curl_log.unlink(missing_ok=True)
                self.assertEqual(self.run_hook(POST_TOOL_USE, env={"DO_NOT_TRACK": value}).returncode, 0)
                self.assertEqual(len(self.sent()), 1)


HOSTS = ("claude-code", "codex", "cursor", "gemini")
NOTICE_URL = "https://fivetran.com/docs/security-and-privacy/telemetry"
EXPANSION = {"hook_event_name": "UserPromptExpansion", "expansion_type": "slash_command",
             "command_name": "fivetran-connector-sdk:build-connector",
             "command_args": "SECRET_ARGS", "prompt": "/fivetran-connector-sdk:build-connector SECRET_ARGS"}


class NoticeTests(HookHarness):
    def notice_text(self, host, stdout):
        out = json.loads(stdout)
        if host == "cursor":
            self.assertIs(out["continue"], True)
            return out["user_message"]
        self.assertEqual(set(out), {"systemMessage"})
        return out["systemMessage"]

    def test_first_run_shows_notice_writes_marker_and_sends_nothing(self):
        for host in HOSTS:
            with self.subTest(host=host):
                self.curl_log.unlink(missing_ok=True)
                result = self.run_hook(POST_TOOL_USE, host=host, mark_shown=False)
                self.assertEqual(result.returncode, 0)
                text = self.notice_text(host, result.stdout)
                for needle in ("DO_NOT_TRACK=1", "FIVETRAN_TELEMETRY_DISABLED=1", NOTICE_URL):
                    self.assertIn(needle, text)
                self.assertTrue(self.marker(host).exists())
                self.assertEqual(self.sent(expect=False), [])

    def test_second_run_sends_event_without_notice(self):
        for host in HOSTS:
            with self.subTest(host=host):
                self.curl_log.unlink(missing_ok=True)
                self.run_hook(POST_TOOL_USE, host=host, mark_shown=False)
                result = self.run_hook(POST_TOOL_USE, host=host, mark_shown=False)
                self.assertEqual(result.stdout.strip(), '{"continue":true}' if host == "cursor" else "")
                [body] = self.sent()
                self.assertEqual(set(body), PAYLOAD_KEYS)

    def test_marker_is_per_host(self):
        self.run_hook(POST_TOOL_USE, host="codex", mark_shown=False)
        result = self.run_hook(POST_TOOL_USE, host="gemini", mark_shown=False)
        self.assertIn("systemMessage", json.loads(result.stdout))
        self.assertTrue(self.marker("codex").exists() and self.marker("gemini").exists())
        self.assertFalse(self.marker("cursor").exists())

    def test_claude_code_without_plugin_data_falls_back_to_home(self):
        env = {"CLAUDE_PLUGIN_DATA": ""}
        result = self.run_hook(POST_TOOL_USE, env=env, mark_shown=False)
        self.assertIn("systemMessage", json.loads(result.stdout))
        self.assertTrue((self.home / ".fivetran/ai-plugins/claude-code/telemetry-notice-shown").exists())

    def test_unwritable_marker_prints_nothing_and_sends_nothing(self):
        blocker = self.home / ".fivetran"
        blocker.write_text("a file where the directory should be")
        result = self.run_hook(POST_TOOL_USE, host="codex", mark_shown=False)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual(self.sent(expect=False), [])

    def test_unwritable_marker_on_cursor_still_continues(self):
        (self.home / ".fivetran").write_text("blocker")
        result = self.run_hook(POST_TOOL_USE, host="cursor", mark_shown=False)
        self.assertEqual(result.stdout.strip(), '{"continue":true}')
        self.assertEqual(self.sent(expect=False), [])

    def test_concurrent_first_runs_show_one_notice(self):
        procs = [subprocess.Popen(
            ["bash", str(HOOK), str(self.manifest), "codex"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            env={**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}",
                 "CURL_LOG": str(self.curl_log), "DO_NOT_TRACK": "", "FIVETRAN_TELEMETRY_DISABLED": ""})
            for _ in range(6)]
        # Feed and close every stdin before waiting on any process, so the hooks overlap.
        for proc in procs:
            proc.stdin.write(json.dumps(POST_TOOL_USE))
            proc.stdin.close()
        outputs = [proc.stdout.read() for proc in procs]
        for proc in procs:
            proc.wait()
            proc.stdout.close()
        self.assertEqual(sum("systemMessage" in out for out in outputs), 1)
        # The hooks that waited for the lock send their event after the notice.
        self.assertEqual(len(self.sent()), len(procs) - 1)

    def test_abandoned_lock_file_does_not_suppress_the_notice(self):
        # flock is released by the OS when a hook dies, so a leftover lock file is harmless.
        lock = Path(str(self.marker("codex")) + ".lock")
        lock.parent.mkdir(parents=True)
        lock.touch()
        result = self.run_hook(POST_TOOL_USE, host="codex", mark_shown=False)
        self.assertIn("systemMessage", json.loads(result.stdout))
        self.assertTrue(self.marker("codex").exists())

    def test_marker_write_failure_after_notice_sends_no_event_and_one_json_object(self):
        # Lock file exists so the hook gets as far as printing; the read-only dir then fails the marker write.
        for host in ("codex", "cursor"):
            with self.subTest(host=host):
                self.curl_log.unlink(missing_ok=True)
                marker_dir = self.marker(host).parent
                marker_dir.mkdir(parents=True, exist_ok=True)
                Path(str(self.marker(host)) + ".lock").touch()
                marker_dir.chmod(0o500)
                self.addCleanup(marker_dir.chmod, 0o700)
                if os.access(marker_dir, os.W_OK):
                    self.skipTest("directory permissions are not enforced (running as root)")
                result = self.run_hook(POST_TOOL_USE, host=host, mark_shown=False)
                self.notice_text(host, result.stdout)  # json.loads fails on a second object
                self.assertFalse(self.marker(host).exists())
                self.assertEqual(self.sent(expect=False), [])

    def test_notice_shows_when_fcntl_is_unavailable(self):
        # Native Windows has no fcntl: the lock is skipped, the notice and marker still work.
        shim = Path(self._tmp.name) / "shim"
        shim.mkdir()
        (shim / "fcntl.py").write_text("raise ImportError('no fcntl')\n")
        result = self.run_hook(POST_TOOL_USE, host="codex", mark_shown=False, env={"PYTHONPATH": str(shim)})
        self.assertIn("systemMessage", json.loads(result.stdout))
        self.assertTrue(self.marker("codex").exists())

    def test_no_notice_for_non_fivetran_events(self):
        other = {**POST_TOOL_USE, "tool_input": {"skill": "other:skill"}}
        result = self.run_hook(other, host="codex", mark_shown=False)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.marker("codex").exists())

    def test_opted_out_run_writes_no_marker_and_cursor_continues(self):
        result = self.run_hook(POST_TOOL_USE, host="cursor", mark_shown=False, env={"DO_NOT_TRACK": "1"})
        self.assertEqual(result.stdout.strip(), '{"continue":true}')
        self.assertFalse(self.marker("cursor").exists())
        self.assertEqual(self.sent(expect=False), [])


class EventTests(HookHarness):
    def test_user_prompt_expansion_sends_command_name_only(self):
        result = self.run_hook(EXPANSION)
        self.assertEqual(result.stdout, "")
        [body] = self.sent()
        self.assertEqual((body["skill"], body["status"]), ("build-connector", "started"))
        self.assertEqual(set(body), PAYLOAD_KEYS)
        self.assertNotIn("SECRET_ARGS", json.dumps(body))

    def test_user_prompt_expansion_ignores_other_commands(self):
        for name in ("other-plugin:build-connector-x", "fivetran-connector-sdk:migrate-meltano-connector", ""):
            with self.subTest(name=name):
                self.run_hook({**EXPANSION, "command_name": name})
                self.assertEqual(self.sent(expect=False), [])
        self.run_hook({**EXPANSION, "command_name": None})
        self.assertEqual(self.sent(expect=False), [])

    def test_non_allowlisted_skill_sends_nothing(self):
        self.run_hook({**POST_TOOL_USE, "tool_input": {"skill": "fivetran-connector-sdk:migrate-meltano-connector"}})
        self.assertEqual(self.sent(expect=False), [])

    def test_post_tool_use_statuses(self):
        self.run_hook(POST_TOOL_USE)
        self.run_hook({**POST_TOOL_USE, "hook_event_name": "PostToolUseFailure"})
        self.assertEqual([b["status"] for b in self.sent()][:1], ["ok"])
        deadline = time.time() + 3
        while len(self.sent()) < 2 and time.time() < deadline:
            time.sleep(0.05)
        self.assertCountEqual([b["status"] for b in self.sent()], ["ok", "fail"])

    def test_prompt_hooks_send_started_for_leading_command_token(self):
        cases = (("UserPromptSubmit", "codex", "$build-connector please"),
                 ("UserPromptSubmit", "codex", "/build-connector please"),
                 ("beforeSubmitPrompt", "cursor", "/fivetran-connector-sdk:test-connector"),
                 ("BeforeAgent", "gemini", "/deploy-connector"))
        for event_name, host, prompt in cases:
            with self.subTest(prompt=prompt):
                self.curl_log.unlink(missing_ok=True)
                self.run_hook({"hook_event_name": event_name, "prompt": prompt}, host=host)
                [body] = self.sent()
                self.assertEqual(body["status"], "started")
                self.assertNotIn("please", json.dumps(body))

    def test_ordinary_prompts_send_nothing(self):
        for prompt in ("hello there", "please run /build-connector", "/some/path/file", ""):
            with self.subTest(prompt=prompt):
                self.run_hook({"hook_event_name": "UserPromptSubmit", "prompt": prompt}, host="codex")
                self.assertEqual(self.sent(expect=False), [])


class BadInputTests(HookHarness):
    def test_invalid_json_sends_nothing(self):
        result = self.run_hook(None, raw="not json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.sent(expect=False), [])

    def test_oversized_payload_sends_nothing(self):
        result = self.run_hook(POST_TOOL_USE, env={"MAX_PAYLOAD_BYTES": "10"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.sent(expect=False), [])

    def test_empty_stdin_sends_nothing(self):
        self.assertEqual(self.run_hook(None, raw="").returncode, 0)
        self.assertEqual(self.sent(expect=False), [])




class ConfigConsistencyTests(unittest.TestCase):
    def test_claude_code_matcher_lists_exactly_the_allowlisted_skills(self):
        import re
        script = HOOK.read_text()
        allowed = set(re.findall(r"'([a-z-]+)'", re.search(r"allowed_skills = \{(.*?)\}", script).group(1)))
        hooks = json.loads((HOOK.parents[2] / "claude-code/hooks/hooks.json").read_text())["hooks"]
        matcher = hooks["UserPromptExpansion"][0]["matcher"]
        listed = set(re.search(r"\((.*)\)", matcher).group(1).split("|"))
        self.assertEqual(listed, allowed)


if __name__ == "__main__":
    unittest.main()
