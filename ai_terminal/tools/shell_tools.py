"""本地 Shell 工具 — 执行本地命令。"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ShellResult:
    """命令执行结果。"""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "success": self.success,
        }


class ShellExecutor:
    """本地命令执行器。"""

    def __init__(
        self,
        timeout: int = 30,
        work_dir: str | None = None,
        env: dict[str, str] | None = None,
    ):
        self.timeout = timeout
        self.work_dir = work_dir or os.getcwd()
        self.env = {**os.environ, **(env or {})}

    async def run(
        self,
        command: str,
        timeout: int | None = None,
        work_dir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ShellResult:
        """执行单条命令。"""
        effective_timeout = timeout or self.timeout
        effective_dir = work_dir or self.work_dir
        effective_env = {**self.env, **(env or {})}

        start = time.monotonic()
        timed_out = False

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_dir,
                env=effective_env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                stdout_bytes, stderr_bytes = b"", b""
                timed_out = True

            duration_ms = int((time.monotonic() - start) * 1000)

            return ShellResult(
                command=command,
                exit_code=process.returncode or (1 if timed_out else 0),
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=duration_ms,
                timed_out=timed_out,
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return ShellResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
            )

    async def run_batch(
        self,
        commands: list[str],
        parallel: bool = False,
        timeout: int | None = None,
    ) -> list[ShellResult]:
        """批量执行命令。"""
        if parallel:
            tasks = [self.run(cmd, timeout=timeout) for cmd in commands]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for cmd in commands:
                result = await self.run(cmd, timeout=timeout)
                results.append(result)
                if not result.success:
                    break  # 串行模式下失败即停止
            return results

    async def run_pipeline(
        self,
        commands: list[str],
        timeout: int | None = None,
    ) -> ShellResult:
        """管道执行：上一条的 stdout 作为下一条的 stdin。"""
        if not commands:
            return ShellResult(command="", exit_code=0, stdout="", stderr="", duration_ms=0)

        # 用 shell 管道语法连接
        pipeline_cmd = " | ".join(commands)
        return await self.run(pipeline_cmd, timeout=timeout)


def register_shell_tools(registry: Any, shell_executor: ShellExecutor | None = None) -> None:
    """注册 Shell 相关工具到 ToolRegistry。"""
    executor = shell_executor or ShellExecutor()

    @registry.tool(
        name="run_command",
        description="在本地终端执行命令。返回 stdout、stderr 和退出码。",
    )
    async def run_command(
        command: str,
        timeout: int = 30,
        work_dir: str | None = None,
    ) -> dict:
        result = await executor.run(command, timeout=timeout, work_dir=work_dir)
        return result.to_dict()

    @registry.tool(
        name="run_pipeline",
        description="执行管道命令（多个命令用 | 连接）。",
    )
    async def run_pipeline(
        commands: list[str],
        timeout: int = 30,
    ) -> dict:
        result = await executor.run_pipeline(commands, timeout=timeout)
        return result.to_dict()

    @registry.tool(
        name="run_batch",
        description="批量执行多条命令。parallel=true 时并行执行。",
    )
    async def run_batch(
        commands: list[str],
        parallel: bool = False,
        timeout: int = 30,
    ) -> dict:
        results = await executor.run_batch(commands, parallel=parallel, timeout=timeout)
        return {
            "results": [r.to_dict() for r in results],
            "all_success": all(r.success for r in results),
        }
