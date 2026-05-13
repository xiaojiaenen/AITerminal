"""远程执行器 — 通过 SSH 在远程主机上执行命令。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

try:
    import asyncssh
except ImportError:
    asyncssh = None  # type: ignore

from ai_terminal.config import HostConfig


@dataclass
class RemoteResult:
    """远程命令执行结果。"""
    host: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    error: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "success": self.success,
            "error": self.error,
        }


class RemoteExecutor:
    """SSH 远程命令执行器。"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._connections: dict[str, Any] = {}

    async def _connect(self, host: HostConfig) -> Any:
        """建立 SSH 连接。"""
        if asyncssh is None:
            raise RuntimeError("asyncssh 未安装，请运行: pip install asyncssh")

        conn_key = f"{host.user}@{host.hostname}:{host.port}"

        # 复用已有连接
        if conn_key in self._connections:
            conn = self._connections[conn_key]
            # 简单检查连接是否还活着
            try:
                await conn.run("echo ok", check=True, timeout=5)
                return conn
            except Exception:
                self._connections.pop(conn_key, None)

        # 建立新连接
        connect_kwargs: dict[str, Any] = {
            "host": host.hostname,
            "port": host.port,
            "username": host.user,
            "known_hosts": None,  # 首次连接不验证 host key
            "connect_timeout": self.timeout,
        }

        if host.key_file:
            connect_kwargs["client_keys"] = [host.key_file]
        elif host.password:
            connect_kwargs["password"] = host.password

        conn = await asyncssh.connect(**connect_kwargs)
        self._connections[conn_key] = conn
        return conn

    async def run_on_host(
        self,
        host: HostConfig,
        command: str,
        timeout: int | None = None,
    ) -> RemoteResult:
        """在单台主机上执行命令。"""
        effective_timeout = timeout or self.timeout
        start = time.monotonic()

        try:
            conn = await self._connect(host)
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=effective_timeout,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            return RemoteResult(
                host=host.name or host.hostname,
                command=command,
                exit_code=result.exit_status,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            return RemoteResult(
                host=host.name or host.hostname,
                command=command,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                timed_out=True,
                error=f"命令超时 ({effective_timeout}s)",
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return RemoteResult(
                host=host.name or host.hostname,
                command=command,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                error=str(e),
            )

    async def run_on_hosts(
        self,
        hosts: list[HostConfig],
        command: str,
        timeout: int | None = None,
        parallel: bool = True,
    ) -> list[RemoteResult]:
        """在多台主机上执行命令。"""
        if parallel:
            tasks = [self.run_on_host(h, command, timeout) for h in hosts]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for host in hosts:
                result = await self.run_on_host(host, command, timeout)
                results.append(result)
            return results

    async def close(self) -> None:
        """关闭所有连接。"""
        for conn in self._connections.values():
            try:
                conn.close()
                await conn.wait_closed()
            except Exception:
                pass
        self._connections.clear()

    async def __aenter__(self) -> "RemoteExecutor":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


def register_cluster_tools(
    registry: Any,
    remote_executor: RemoteExecutor | None = None,
    inventory: Any = None,
) -> None:
    """注册集群相关工具到 ToolRegistry。"""
    executor = remote_executor or RemoteExecutor()

    @registry.tool(
        name="remote_run",
        description="在远程主机上执行命令。target 可以是主机名、组名或 'all'。",
    )
    async def remote_run(
        command: str,
        target: str = "all",
        timeout: int = 30,
        parallel: bool = True,
    ) -> dict:
        if inventory is None:
            return {"error": "未配置主机清单"}

        hosts = inventory.get_hosts(target)
        if not hosts:
            return {"error": f"未找到目标主机: {target}"}

        results = await executor.run_on_hosts(hosts, command, timeout=timeout, parallel=parallel)
        return {
            "results": [r.to_dict() for r in results],
            "total": len(results),
            "success_count": sum(1 for r in results if r.success),
            "fail_count": sum(1 for r in results if not r.success),
        }

    @registry.tool(
        name="remote_upload",
        description="上传文件到远程主机。",
    )
    async def remote_upload(
        local_path: str,
        remote_path: str,
        target: str = "all",
    ) -> dict:
        if asyncssh is None:
            return {"error": "asyncssh 未安装"}
        if inventory is None:
            return {"error": "未配置主机清单"}

        hosts = inventory.get_hosts(target)
        if not hosts:
            return {"error": f"未找到目标主机: {target}"}

        results = []
        for host in hosts:
            try:
                conn = await executor._connect(host)
                await asyncssh.scp(local_path, (conn, remote_path))
                results.append({"host": host.name, "success": True})
            except Exception as e:
                results.append({"host": host.name, "success": False, "error": str(e)})

        return {"results": results}

    @registry.tool(
        name="list_hosts",
        description="列出所有已配置的主机。",
    )
    async def list_hosts() -> dict:
        if inventory is None:
            return {"hosts": [], "groups": {}}

        return {
            "hosts": [
                {
                    "name": h.name,
                    "hostname": h.hostname,
                    "port": h.port,
                    "user": h.user,
                    "tags": h.tags,
                }
                for h in inventory.hosts
            ],
            "groups": inventory.groups,
        }
