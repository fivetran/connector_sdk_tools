"""Deployment target and non-interactive boundaries; never contact a real account."""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / "canonical/tools/deploy_connector.py"


@unittest.skipUnless(os.name == "posix", "Fake SDK executable uses a POSIX shebang")
class DeployTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("deploy_fixture", HELPER)
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "recovered_directory"
        self.project.mkdir()
        (self.project / "configuration.json").write_text('{"zip_codes":"90210"}')
        executable = self.project / ".venv/bin/fivetran"
        executable.parent.mkdir(parents=True)
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "assert sys.argv[1] == 'deploy'\n"
            "assert '--api-key' not in sys.argv\n"
            "assert os.environ['FIVETRAN_API_KEY'] == 'Zml4dHVyZTpmaXh0dXJl'\n"
            "if '--configuration' in sys.argv:\n"
            "    with open(sys.argv[sys.argv.index('--configuration')+1]) as stream:\n"
            "        pathlib.Path('submitted-config.json').write_text(json.dumps(json.load(stream)))\n"
            "pathlib.Path('environment-config.json').write_text(json.dumps(os.getenv('FIVETRAN_CONFIGURATION')))\n"
            "pathlib.Path('invocation.json').write_text(json.dumps(sys.argv[1:]))\n"
            "print('Connection ID: existing_id')\n"
        )
        executable.chmod(0o700)
        self.requests = []
        self.connection = {"service": "connector_sdk", "schema": "original_name",
                           "group_id": "original_group"}

    def get(self, path, _key):
        self.requests.append(path)
        responses = {
            "/connections/existing_id": {"data": self.connection},
            "/groups/original_group": {"data": {"name": "Original Destination"}},
        }
        return responses[path]  # Any list/discovery request is a test failure.

    def run_main(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", [str(HELPER), str(self.project), *args]), \
             patch.dict(os.environ, {"FIVETRAN_API_KEY": "Zml4dHVyZTpmaXh0dXJl"}), \
             patch.object(self.helper, "fivetran_get", self.get), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit) as error:
                self.helper.main()
        self.output = output.getvalue()
        return error.exception.code

    def invocation(self):
        return json.loads((self.project / "invocation.json").read_text())

    def test_existing_connection_uses_its_own_name_and_destination(self):
        self.assertEqual(self.run_main("--connection-id", "existing_id"), 0)
        self.assertEqual(self.requests, ["/connections/existing_id", "/groups/original_group"])
        args = self.invocation()
        self.assertEqual(args[args.index("--connection") + 1], "original_name")
        self.assertEqual(args[args.index("--destination") + 1], "Original Destination")
        self.assertFalse((self.project / ".config_pipe").exists())
        self.assertEqual(json.loads((self.project / "submitted-config.json").read_text()),
                         {"zip_codes": "90210"})

    def test_missing_local_configuration_defers_to_sdk(self):
        (self.project / "configuration.json").unlink()
        for value in (None, '{"zip_codes":"10001"}'):
            with self.subTest(environment=value), patch.dict(os.environ):
                os.environ.pop("FIVETRAN_CONFIGURATION", None)
                if value is not None:
                    os.environ["FIVETRAN_CONFIGURATION"] = value
                self.assertEqual(self.run_main("--connection-id", "existing_id"), 0)
                self.assertNotIn("--configuration", self.invocation())
                self.assertFalse((self.project / "configuration.json").exists())
                self.assertFalse((self.project / "submitted-config.json").exists())
                self.assertEqual(json.loads((self.project / "environment-config.json").read_text()), value)

    def test_explicit_new_destination_needs_no_discovery(self):
        self.assertEqual(self.run_main("--destination", "Chosen Group", "--connection", "new"), 0)
        self.assertEqual(self.requests, [])
        args = self.invocation()
        self.assertEqual(args[args.index("--destination") + 1], "Chosen Group")
        self.assertEqual(args[args.index("--connection") + 1], "new")

    def test_new_deploy_without_connection_id_keeps_sync_guidance(self):
        executable = self.project / ".venv/bin/fivetran"
        executable.write_text(executable.read_text().replace(
            "print('Connection ID: existing_id')", "print('Deployment succeeded')"))
        with patch.object(self.helper, "unpause_connection") as unpause:
            self.assertEqual(self.run_main("--destination", "Chosen Group"), 0)
            unpause.assert_not_called()
        self.assertEqual(self.requests, [])
        self.assertIn("paused", self.output)
        self.assertIn("initial sync (consumes MAR)", self.output)
        self.assertIn("confirming with the user", self.output)
        self.assertIn("dashboard", self.output)
        self.assertIn('--start-sync --connection-id "<connection_id>"', self.output)
        self.assertNotIn("Deployed. Connection ID:", self.output)

    def test_invalid_existing_target_never_deploys(self):
        for connection in ({"service": "postgres"}, {"service": "connector_sdk"}):
            with self.subTest(connection=connection):
                self.connection = connection
                self.assertEqual(self.run_main("--connection-id", "existing_id"), 1)
                self.assertFalse((self.project / "invocation.json").exists())
        for option in ("--connection", "--destination"):
            with self.subTest(option=option):
                self.assertEqual(self.run_main("--connection-id", "existing_id", option, "other"), 2)
                self.assertFalse((self.project / "invocation.json").exists())

    def test_closed_input_exits_without_retry(self):
        with patch("builtins.input", side_effect=EOFError) as prompt, \
             contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                self.helper.pick_one([{"name": "a"}, {"name": "b"}],
                                     lambda item: item["name"], "Choose", "destination")
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(prompt.call_count, 1)

    def test_piped_selection_still_works_after_invalid_input(self):
        items = [{"name": "a"}, {"name": "b"}]
        with patch.object(sys, "stdin", io.StringIO("invalid\n9\n2\n")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                self.helper.pick_one(items, lambda item: item["name"], "Choose", "destination"),
                items[1],
            )

    def test_interactive_terminal_selection_still_works(self):
        import pty
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        with os.fdopen(slave) as terminal, patch.object(sys, "stdin", terminal), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(terminal.isatty())
            os.write(master, b"1\n")
            self.assertEqual(
                self.helper.pick_one(["a", "b"], str, "Choose", "destination"), "a",
            )

    def test_single_destination_needs_no_input(self):
        with patch("builtins.input", side_effect=AssertionError("unexpected prompt")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.helper.pick_one(["a"], str, "Choose", "destination"), "a")

    def test_start_sync_remains_explicit(self):
        with patch.object(self.helper, "unpause_connection") as unpause:
            self.assertEqual(self.run_main("--start-sync", "--connection-id", "existing_id"), 0)
            self.assertEqual(unpause.call_args.args[1], "existing_id")
        self.assertFalse((self.project / "invocation.json").exists())
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
