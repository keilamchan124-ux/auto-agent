# mcp/python_executor/python_executor.py

import subprocess
import os
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    returncode: int
    success: bool
    command: str

class PythonExecutorMCP:
    """
    Python Executor MCP - 讓 Agent 可以安全執行 Python 程式碼
    """

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.working_directory = os.getcwd()

    def run_code(self, code: str, cwd: Optional[str] = None) -> ExecutionResult:
        """執行 Python 程式碼片段（使用 python -c）"""
        command = f'python -c "{code}"'
        return self._execute(command, cwd)

    def run_script(self, script_path: str, args: Optional[List[str]] = None, cwd: Optional[str] = None) -> ExecutionResult:
        """執行 Python 腳本檔案"""
        cmd = ["python", script_path] + (args or [])
        return self._execute(cmd, cwd)

    def _execute(self, command, cwd: Optional[str] = None) -> ExecutionResult:
        try:
            result = subprocess.run(
                command,
                shell=isinstance(command, str),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd or self.working_directory
            )
            return ExecutionResult(
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                returncode=result.returncode,
                success=result.returncode == 0,
                command=str(command)
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="",
                stderr=f"執行超時（超過 {self.timeout} 秒）",
                returncode=-1,
                success=False,
                command=str(command)
            )
        except Exception as e:
            return ExecutionResult(
                stdout="",
                stderr=str(e),
                returncode=-1,
                success=False,
                command=str(command)
            )

    def set_working_directory(self, path: str):
        """設定執行時的工作目錄"""
        if os.path.isdir(path):
            self.working_directory = os.path.abspath(path)
        else:
            raise ValueError(f"目錄不存在: {path}")