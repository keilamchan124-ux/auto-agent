import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys
import os
from types import ModuleType
import re

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("MIMO_API_KEY", "test-key")

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

import main
from core.agent import Agent
from core import tools as core_tools
from core.config import Config


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


class TraceSummaryRegressionTests(unittest.TestCase):
    def test_analyze_current_task_trace_counts_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            trace_dir = workspace / "artifacts" / "traces"
            trace_dir.mkdir(parents=True, exist_ok=True)
            task_id = "task_123"
            trace_path = trace_dir / f"{task_id}.jsonl"
            rows = [
                {"task_id": task_id, "action": "plan", "result": {"ok": True}},
                {"task_id": task_id, "action": "run_cmd", "result": {"ok": False}},
                {"task_id": task_id, "action": "run_cmd", "result": {"ok": False}},
            ]
            trace_path.write_text("\n".join(json.dumps(r) for r in rows), "utf-8")

            agent = Agent.__new__(Agent)
            agent.current_task_id = task_id
            with mock.patch("core.agent.Config.WORKSPACE_DIR", workspace):
                summary = Agent._analyze_current_task_trace(agent)

            self.assertEqual(summary["total_steps"], 3)
            self.assertEqual(summary["failed_steps"], 2)
            self.assertEqual(summary["top_failed_actions"][0][0], "run_cmd")


class ToolRegressionTests(unittest.TestCase):
    def test_design_to_component_metadata_generates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", workspace):
                raw = core_tools.design_to_component_metadata(
                    design_name="demo",
                    screens=["home", {"name": "settings", "purpose": "preferences"}],
                    output_path="design/meta.json",
                )
            data = json.loads(raw)
            self.assertTrue(data["ok"])
            self.assertTrue((workspace / "design" / "meta.json").exists())

    def test_capture_web_screenshot_reports_dependency_error_without_playwright(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", workspace):
                with mock.patch.dict(sys.modules, {"playwright.sync_api": None}):
                    raw = core_tools.capture_web_screenshot(
                        url="http://127.0.0.1:8787",
                        output_path="artifacts/screen.png",
                    )
            data = json.loads(raw)
            self.assertFalse(data["ok"])

    def test_start_web_server_writes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            target = workspace / "build" / "web"
            target.mkdir(parents=True, exist_ok=True)

            fake_proc = mock.Mock()
            fake_proc.pid = 4321
            fake_proc.poll.return_value = None

            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", workspace):
                with mock.patch("core.tools.subprocess.Popen", return_value=fake_proc):
                    with mock.patch("core.tools.requests.get") as get_mock:
                        get_mock.return_value.status_code = 200
                        raw = core_tools.start_web_server(project_dir="build/web", host="127.0.0.1", port=8787, task_id="task_1")

            data = json.loads(raw)
            self.assertTrue(data["ok"])
            self.assertEqual(data["data"]["pid"], 4321)
            self.assertTrue(data["data"]["healthy"])
            self.assertTrue((workspace / "artifacts" / "web_server_task_1_8787.json").exists())

    def test_stop_web_server_removes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            meta_dir = workspace / "artifacts"
            meta_dir.mkdir(parents=True, exist_ok=True)
            (meta_dir / "web_server_default_8787.json").write_text(json.dumps({"pid": 999999}), "utf-8")
            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", workspace):
                raw = core_tools.stop_web_server()
            data = json.loads(raw)
            self.assertTrue(data["ok"])
            self.assertTrue(data["data"]["stopped"])
            self.assertFalse((meta_dir / "web_server_default_8787.json").exists())

    def test_web_server_status_reports_log_tails(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            logs_dir = workspace / "artifacts" / "web_server_logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            (logs_dir / "stdout.log").write_text("line1\nline2\n", "utf-8")
            (logs_dir / "stderr.log").write_text("err1\n", "utf-8")
            meta_path = workspace / "artifacts" / "web_server_default_8787.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "url": "http://127.0.0.1:8787",
                        "stdout_log": "artifacts/web_server_logs/stdout.log",
                        "stderr_log": "artifacts/web_server_logs/stderr.log",
                    }
                ),
                "utf-8",
            )
            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", workspace):
                with mock.patch("core.tools.requests.get") as get_mock:
                    get_mock.return_value.status_code = 200
                    raw = core_tools.web_server_status()
            data = json.loads(raw)
            self.assertTrue(data["ok"])
            self.assertIn("line2", data["data"]["stdout_tail"])



class PromptRegistryConsistencyTests(unittest.TestCase):
    def test_prompt_actions_exist_in_registry(self):
        prompt = Config._BASE_PROMPT
        listed_actions = set()
        for line in prompt.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith("|---") or line.startswith("| Action"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            cell = parts[1]
            for part in cell.split(","):
                action = part.strip()
                if action:
                    listed_actions.add(action)
        listed_actions.discard("git_commit")
        listed_actions.discard("mark_done")
        missing = [a for a in sorted(listed_actions) if a not in core_tools.TOOLS_REGISTRY]
        self.assertEqual(missing, [])

    def test_prompt_parameter_schema_examples_present(self):
        prompt = Config._BASE_PROMPT
        self.assertIn('run_cmd → {"cmd": "ls -la"}', prompt)
        self.assertIn('plan","kwargs":{"steps"', prompt)
        self.assertIn('get_skill","kwargs":{"skill_name"', prompt)

    def test_rescue_error_code_semantics(self):
        import core.llm as core_llm
        self.assertEqual(core_llm._classify_error_code("401 Unauthorized"), "auth_error")
        self.assertEqual(core_llm._classify_error_code("404 not found"), "not_found")
        self.assertEqual(core_llm._classify_error_code("429 rate limited"), "rate_limited")
        self.assertEqual(core_llm._classify_error_code("HTTP 500"), "http_error")

    def test_mcp_registry_alias_and_dedup(self):
        import core.mcp_registry as mcp_registry
        with mock.patch.dict(os.environ, {"MCP_SERVERS": "chrome,devtools,codegen,visual,semgrep"}, clear=False):
            items = mcp_registry.get_enabled_mcp_registry()
        names = [i["name"] for i in items]
        self.assertIn("chrome-devtools", names)
        self.assertIn("codegeneratormcp", names)
        self.assertIn("web-visual-feedback", names)
        self.assertIn("semgrep", names)
        self.assertEqual(names.count("chrome-devtools"), 1)

    def test_workspace_path_canonicalizer(self):
        self.assertEqual(core_tools._canonicalize_workspace_path("workspace/workspace/demo/x.py"), "workspace/demo/x.py")
        self.assertEqual(core_tools._canonicalize_workspace_path("workspace\\workspace\\demo\\x.py"), "workspace/demo/x.py")

    def test_rescue_decision_matrix_returns_predictable_actions(self):
        import core.llm as core_llm
        self.assertEqual(core_llm.get_rescue_decision("auth_error")["action"], "run_cmd")
        self.assertEqual(core_llm.get_rescue_decision("not_found")["action"], "read_file")
        self.assertEqual(core_llm.get_rescue_decision("rate_limited")["action"], "plan")

    def test_policy_gate_phase_and_completion_lock(self):
        from core.policy_gate import PolicyGate
        gate = PolicyGate(phase_window=3)
        self.assertTrue(gate.is_ui_verify_phase(3))
        self.assertFalse(gate.is_ui_verify_phase(2))
        self.assertTrue(gate.enforce_mcp_phase_hard_gate("capture_web_screenshot", True))
        self.assertFalse(gate.enforce_mcp_phase_hard_gate("download_file", True))
        self.assertFalse(gate.enforce_completion_lock("mark_done", True))

    def test_agent_mcp_usage_floor_requires_github_action_early(self):
        agent = Agent.__new__(Agent)
        enabled = [{"name": "github", "role": "repo context"}]
        ok, _ = Agent._enforce_mcp_usage_floor(agent, "plan", 2, "please update this github repo issue", enabled)
        self.assertTrue(ok)
        ok2, msg2 = Agent._enforce_mcp_usage_floor(agent, "write_file", 2, "please update this github repo issue", enabled)
        self.assertFalse(ok2)
        self.assertIn("MCP_USAGE_REQUIRED", msg2)


@unittest.skipUnless(os.getenv("RUN_SMOKE_INTEGRATION") == "1", "Smoke integration is optional and env-gated.")
class SmokeIntegrationTests(unittest.TestCase):
    def test_playwright_and_flutter_quality_gate_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            app_dir = workspace / "app"
            app_dir.mkdir(parents=True, exist_ok=True)
            web_dir = workspace / "build" / "web"
            web_dir.mkdir(parents=True, exist_ok=True)
            (web_dir / "index.html").write_text("<html><body><h1>smoke</h1></body></html>", "utf-8")
            with mock.patch.object(core_tools.Config, "WORKSPACE_DIR", workspace):
                start_result = json.loads(core_tools.start_web_server(project_dir="build/web", port=8788, task_id="smoke"))
                self.assertTrue(start_result.get("ok"))
                self.assertTrue(start_result["data"].get("healthy"))

                shot = json.loads(
                    core_tools.capture_web_screenshot(
                        url="http://127.0.0.1:8788",
                        output_path="artifacts/smoke.png",
                        wait_ms=200,
                    )
                )
                self.assertTrue(shot.get("ok"))
                self.assertTrue((workspace / "artifacts" / "smoke.png").exists())

                quality_result = json.loads(
                    core_tools.validate_mobile_quality(
                        project_dir="app",
                        include_web=True,
                        strict_web=True,
                    )
                )
                steps = [r["step"] for r in quality_result.get("data", {}).get("results", [])]
                self.assertIn("flutter pub get", steps)
                self.assertIn("flutter build web", steps)
                stopped = json.loads(core_tools.stop_web_server(meta_path="artifacts/web_server_smoke_8788.json"))
                self.assertTrue(stopped.get("ok"))


if __name__ == "__main__":
    unittest.main()
