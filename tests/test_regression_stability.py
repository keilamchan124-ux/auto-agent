import os
import sys
import tempfile
import unittest
import subprocess
import importlib.util
from pathlib import Path
from types import ModuleType
from unittest import mock
import json

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("MIMO_API_KEY", "test-key")

if "tools" not in sys.modules:
    tools_stub = ModuleType("tools")
    tools_stub.execute_tool = lambda action, kwargs: "{}"
    sys.modules["tools"] = tools_stub

from agent import Agent
import main

if "ddgs" not in sys.modules:
    ddgs_stub = ModuleType("ddgs")
    ddgs_stub.DDGS = object
    sys.modules["ddgs"] = ddgs_stub

if "markitdown" not in sys.modules:
    markitdown_stub = ModuleType("markitdown")
    class _DummyMarkItDown:
        def convert(self, _):
            class _R:
                text_content = ""
            return _R()
    markitdown_stub.MarkItDown = _DummyMarkItDown
    sys.modules["markitdown"] = markitdown_stub

_tools_spec = importlib.util.spec_from_file_location("core.tools", Path(__file__).resolve().parents[1] / "core" / "tools.py")
core_tools = importlib.util.module_from_spec(_tools_spec)
assert _tools_spec and _tools_spec.loader
_tools_spec.loader.exec_module(core_tools)


class AgentHistoryRegressionTests(unittest.TestCase):
    def test_smart_summarize_history_returns_short_history_directly(self):
        agent = Agent.__new__(Agent)
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "c"},
            {"role": "user", "content": "d"},
        ]

        with mock.patch("agent.llm.call_gemini_rescue") as rescue_mock:
            result = Agent.smart_summarize_history(agent, msgs)

        self.assertEqual(result, msgs)
        rescue_mock.assert_not_called()


class SingleInstanceLockRegressionTests(unittest.TestCase):
    def test_single_instance_removes_stale_lock_and_rewrites_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "agent.lock"
            lock_path.write_text("999999", encoding="utf-8")

            with mock.patch.object(main, "LOCK_FILE", str(lock_path)):
                with mock.patch("main._is_pid_running", return_value=False):
                    main.single_instance()

            new_pid = lock_path.read_text(encoding="utf-8").strip()
            self.assertTrue(new_pid.isdigit())
            self.assertNotEqual(new_pid, "999999")

    def test_single_instance_exits_when_live_pid_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "agent.lock"
            lock_path.write_text("12345", encoding="utf-8")

            with mock.patch.object(main, "LOCK_FILE", str(lock_path)):
                with mock.patch("main._is_pid_running", return_value=True):
                    with self.assertRaises(SystemExit) as ctx:
                        main.single_instance()

            self.assertEqual(ctx.exception.code, 1)


class LeanModeToolTests(unittest.TestCase):
    def test_github_read_file_supports_line_range_and_lean_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "workspace" / "repo"
            repo.mkdir(parents=True, exist_ok=True)
            target = repo / "demo.txt"
            target.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", (Path(tmp) / "workspace")):
                raw = core_tools.github_read_file("repo", "demo.txt", max_chars=3, lean_mode=True, start_line=2, end_line=4)
                data = json.loads(raw)

            self.assertTrue(data["ok"])
            self.assertEqual(data["data"]["range"]["start_line"], 2)
            self.assertEqual(data["data"]["content"], "b\nc\nd")

    def test_github_commit_push_lean_mode_returns_compact_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "workspace" / "repo"
            repo.mkdir(parents=True, exist_ok=True)

            cp = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="ok", stderr="")
            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", (Path(tmp) / "workspace")):
                with mock.patch("core.tools.subprocess.run", return_value=cp) as run_mock:
                    raw = core_tools.github_commit_push("repo", "msg", branch="feat/x", lean_mode=True)
                    data = json.loads(raw)

            self.assertTrue(data["ok"])
            self.assertIn("steps", data["data"])
            self.assertGreaterEqual(len(data["data"]["steps"]), 3)
            self.assertTrue(run_mock.called)


if __name__ == "__main__":
    unittest.main()
