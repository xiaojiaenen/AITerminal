# AI Terminal — 架构设计方案

基于 Wuwei Agent 框架构建的 AI 终端管家，类似 Claude Code / Warp AI，专注于终端操作与集群运维。

## 1. 项目定位

**一句话描述：** 用自然语言操作终端、管理集群的 AI 管家。

**核心场景：**

- 用户说"看看 192.168.1.10 这台机器的磁盘使用率" → Agent 执行 `ssh user@192.168.1.10 df -h`
- 用户说"把所有 Web 服务器的 nginx 重启" → Agent 批量执行，每台先确认
- 用户说"最近有什么异常日志" → Agent 搜索多台机器的 syslog，汇总报告
- 用户说"帮我部署最新版本" → Agent 执行 git pull + build + restart 流水线

**安全红线：**

- 永远不自动执行删除、覆盖、格式化等破坏性操作
- 涉及多台机器的操作必须逐台确认
- 所有操作可回溯、可审计

## 2. 整体架构

```
AI-Terminal/
├── ai_terminal/
│   ├── __init__.py
│   ├── app.py                  # 主入口，交互式 CLI
│   ├── config.py               # 配置管理（集群、凭证、安全策略）
│   ├── safety/
│   │   ├── __init__.py
│   │   ├── policy.py           # 安全策略引擎
│   │   ├── sandbox.py          # 命令沙箱
│   │   ├── audit.py            # 审计日志
│   │   └── rollback.py         # 回滚机制
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── shell_tools.py      # 本地 Shell 工具
│   │   ├── ssh_tools.py        # SSH 远程执行工具
│   │   ├── cluster_tools.py    # 集群批量操作工具
│   │   ├── file_tools.py       # 远程文件操作工具
│   │   ├── monitor_tools.py    # 监控/诊断工具
│   │   └── deploy_tools.py     # 部署工具
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── safety_hook.py      # 安全审批 Hook
│   │   ├── audit_hook.py       # 审计 Hook
│   │   ├── cluster_hook.py     # 集群上下文 Hook
│   │   └── history_hook.py     # 命令历史 Hook
│   ├── cluster/
│   │   ├── __init__.py
│   │   ├── manager.py          # 集群管理器
│   │   ├── inventory.py        # 主机清单
│   │   └── ssh_pool.py         # SSH 连接池
│   └── knowledge/
│       ├── __init__.py
│       ├── runbook_store.py    # 运维知识库
│       ├── context_hook.py     # 知识检索 Hook
│       ├── incident_recorder.py # 踩坑事件记录
│       ├── skill_generator.py  # 从事件生成 Skill
│       └── incident_hook.py    # 自动沉淀 Hook
├── docs/
│   ├── architecture.md         # 本文档
│   ├── safety.md               # 安全设计
│   └── tools.md                # 工具清单
├── tests/
├── pyproject.toml
└── README.md
```

## 3. 安全体系（核心设计）

安全是这个项目的第一优先级。不是附加功能，是架构的核心。

### 3.1 命令分级

所有命令按风险分为四级：

| 级别 | 说明 | 处理方式 |
|------|------|----------|
| **SAFE** | 只读操作 | 自动执行 |
| **LOW** | 写入但可逆 | 显示命令，自动执行 |
| **HIGH** | 破坏性但有备份路径 | 必须用户确认 |
| **CRITICAL** | 不可逆破坏性操作 | 必须用户确认 + 二次确认 |

**分级规则（内置 + 可扩展）：**

```python
# SAFE — 只读
SAFE_PATTERNS = [
    r"^ls\b", r"^cat\b", r"^head\b", r"^tail\b", r"^grep\b",
    r"^find\b", r"^du\b", r"^df\b", r"^ps\b", r"^top\b",
    r"^free\b", r"^uptime\b", r"^whoami\b", r"^hostname\b",
    r"^ip addr\b", r"^ping\b", r"^curl\b.*--head",  # HEAD 请求
    r"^systemctl status\b", r"^journalctl\b",
    r"^docker ps\b", r"^docker logs\b", r"^docker inspect\b",
]

# LOW — 写入但可逆
LOW_PATTERNS = [
    r"^touch\b", r"^mkdir\b", r"^cp\b", r"^mv\b",
    r"^echo\b.*>>",  # 追加
    r"^docker run\b", r"^docker start\b", r"^docker stop\b",
    r"^systemctl start\b", r"^systemctl restart\b",
    r"^git (add|commit|push|pull|checkout|branch)\b",
    r"^pip install\b", r"^npm install\b",
]

# HIGH — 破坏性但有备份路径
HIGH_PATTERNS = [
    r"^rm\b", r"^rmdir\b",
    r"^echo\b.*>(?!>)",  # 覆盖写入（非追加）
    r"^docker rm\b", r"^docker kill\b",
    r"^systemctl stop\b", r"^systemctl disable\b",
    r"^git reset\b.*--hard", r"^git clean\b",
    r"^iptables\b", r"^ufw\b",
    r"^userdel\b", r"^groupdel\b",
]

# CRITICAL — 不可逆
CRITICAL_PATTERNS = [
    r"^rm\s+-rf\s+/",           # 根目录递归删除
    r"^mkfs\b",                  # 格式化
    r"^dd\b",                    # 底层写入
    r"^fdisk\b",                 # 分区操作
    r"^shutdown\b", r"^reboot\b",
    r"^drop database\b", r"^truncate\b",  # SQL
    r"^docker system prune\b.*-a",  # 清理所有 Docker 资源
    r"> /dev/sd",                # 直接写磁盘
]
```

### 3.2 安全策略引擎

```python
# ai_terminal/safety/policy.py

from enum import Enum

class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"

class SafetyPolicy:
    """安全策略引擎 — 决定一个命令能不能执行、怎么执行。"""

    def __init__(self, config: dict):
        # 是否允许远程执行
        self.allow_remote = config.get("allow_remote", True)
        # 是否允许批量执行
        self.allow_batch = config.get("allow_batch", True)
        # 自定义白名单（跳过所有检查直接执行）
        self.whitelist: set[str] = set(config.get("whitelist", []))
        # 自定义黑名单（直接拒绝）
        self.blacklist: set[str] = set(config.get("blacklist", []))
        # 批量操作时最多同时操作几台机器
        self.max_batch_size = config.get("max_batch_size", 5)
        # 命令超时秒数
        self.command_timeout = config.get("command_timeout", 30)

    def classify(self, command: str) -> RiskLevel:
        """判断命令的风险等级。"""
        ...

    def check(self, command: str, target: str = "local") -> Decision:
        """
        检查命令是否允许执行。

        返回 Decision:
        - allowed: bool
        - risk_level: RiskLevel
        - reason: str
        - require_confirmation: bool
        - require_rollback_plan: bool
        """
        ...
```

### 3.3 执行前确认流程

```
用户: "删除 /tmp 下 7 天前的日志文件"

Agent 生成命令: find /tmp -name "*.log" -mtime +7 -delete

SafetyPolicy.check() → HIGH（rm 相关）

终端显示:
┌─────────────────────────────────────────────────┐
│  [HIGH] 即将执行破坏性操作                       │
│                                                  │
│  命令: find /tmp -name "*.log" -mtime +7 -delete │
│  目标: 本地                                      │
│  风险: 删除文件，不可逆                           │
│                                                  │
│  建议替代方案:                                    │
│  find /tmp -name "*.log" -mtime +7 -exec mv {} /tmp/trash/ \; │
│                                                  │
│  [y] 确认执行  [n] 取消  [a] 使用替代方案  [e] 编辑命令 │
└─────────────────────────────────────────────────┘
```

**关键设计：**

- HIGH/CRITICAL 级别命令，Agent 必须同时提供安全的替代方案
- 用户可以选择"使用替代方案"一键替换
- 用户可以"编辑命令"手动修改后再执行
- CRITICAL 级别需要二次确认（输入 yes）

### 3.4 批量操作安全

```
用户: "重启所有 Web 服务器的 nginx"

Agent 生成批量命令:
  web-01: systemctl restart nginx
  web-02: systemctl restart nginx
  web-03: systemctl restart nginx

终端显示:
┌─────────────────────────────────────────────────┐
│  [BATCH] 批量操作 — 3 台服务器                    │
│                                                  │
│  web-01: systemctl restart nginx     [MEDIUM]    │
│  web-02: systemctl restart nginx     [MEDIUM]    │
│  web-03: systemctl restart nginx     [MEDIUM]    │
│                                                  │
│  执行策略: 逐台执行，每台间隔 5 秒                │
│  失败策略: 任一失败则暂停，等待指示                │
│                                                  │
│  [y] 全部执行  [s] 逐台确认  [n] 取消             │
└─────────────────────────────────────────────────┘
```

**批量操作规则：**

- 最多同时操作 `max_batch_size` 台机器（默认 5）
- 逐台执行，不并行（方便观察和中断）
- 任一失败立即暂停，等待用户指示
- 提供"跳过失败继续"和"回滚已完成"选项
- CRITICAL 级别命令在批量模式下禁止执行

### 3.5 审计日志

所有操作记录到审计日志，不可篡改：

```json
{
  "timestamp": "2026-05-13T10:30:00Z",
  "session_id": "abc123",
  "user_input": "重启 nginx",
  "command": "systemctl restart nginx",
  "target": "web-01",
  "risk_level": "LOW",
  "decision": "approved",
  "confirmed_by": "user",
  "output": "Restarting nginx...",
  "exit_code": 0,
  "duration_ms": 1200,
  "rollback_command": "systemctl start nginx"
}
```

审计日志存储位置：`~/.ai-terminal/audit/YYYY-MM-DD.jsonl`

### 3.6 回滚机制

对于 HIGH 级别操作，Agent 必须在执行前生成回滚命令：

| 操作 | 回滚命令 |
|------|----------|
| `rm file` | 无（先 mv 到 trash） |
| `systemctl stop nginx` | `systemctl start nginx` |
| `docker rm container` | `docker run ...` (记录原始参数) |
| `git reset --hard` | `git reflog` 找回 |
| `iptables -F` | 从备份恢复规则 |

执行前自动备份相关状态，执行失败时提供一键回滚。

## 4. 工具系统

### 4.1 Shell 工具（本地）

```python
@registry.tool(
    name="run_command",
    description="在本地执行 Shell 命令。读取文件、查看状态等只读操作自动执行；写入操作需要确认。",
    side_effect=True,
)
async def run_command(command: str, cwd: str | None = None) -> dict:
    """
    执行本地命令，返回:
    - ok: bool
    - stdout: str
    - stderr: str
    - exit_code: int
    - risk_level: str
    - duration_ms: int
    """
    ...
```

### 4.2 SSH 工具（远程）

```python
@registry.tool(
    name="ssh_exec",
    description="在远程服务器上执行命令。需要指定 host 和命令。",
    side_effect=True,
)
async def ssh_exec(host: str, command: str, user: str | None = None) -> dict:
    """
    通过 SSH 在远程执行命令。
    连接信息从集群配置中读取，不需要用户输入密码。
    """
    ...
```

### 4.3 集群批量工具

```python
@registry.tool(
    name="cluster_exec",
    description="在集群中多台服务器上执行同一命令。支持按角色、标签筛选目标。",
    side_effect=True,
    requires_approval=True,  # 批量操作始终需要审批
)
async def cluster_exec(
    command: str,
    targets: str = "all",      # "all", "web", "db", "web-01,web-02"
    strategy: str = "serial",  # serial | parallel | rolling
    max_parallel: int = 5,
) -> dict:
    """
    批量执行，返回每台机器的执行结果。
    """
    ...
```

### 4.4 监控诊断工具

```python
@registry.tool(
    name="system_status",
    description="查看系统状态：CPU、内存、磁盘、网络、进程。支持本地和远程。",
)
async def system_status(host: str = "local") -> dict:
    ...

@registry.tool(
    name="check_logs",
    description="搜索系统日志，支持关键词、时间范围、严重级别过滤。支持多台机器。",
)
async def check_logs(
    keyword: str,
    hosts: str = "local",
    since: str = "1h",      # 1h, 30m, 2026-05-13
    level: str = "error",   # error, warn, info
    limit: int = 50,
) -> dict:
    ...

@registry.tool(
    name="check_port",
    description="检查端口是否在监听，支持多台机器批量检查。",
)
async def check_port(port: int, hosts: str = "all") -> dict:
    ...
```

### 4.5 部署工具

```python
@registry.tool(
    name="deploy",
    description="执行部署流程。需要指定部署目标和版本。始终需要确认。",
    side_effect=True,
    requires_approval=True,
)
async def deploy(
    service: str,
    version: str = "latest",
    targets: str = "all",
    strategy: str = "rolling",  # rolling | blue-green | canary
) -> dict:
    ...
```

## 5. 集群管理

### 5.1 主机清单配置

`~/.ai-terminal/inventory.yaml`：

```yaml
clusters:
  web:
    hosts:
      - name: web-01
        host: 192.168.1.10
        user: deploy
        port: 22
        tags: [nginx, node]
      - name: web-02
        host: 192.168.1.11
        user: deploy
        port: 22
        tags: [nginx, node]
      - name: web-03
        host: 192.168.1.12
        user: deploy
        port: 22
        tags: [nginx, node]

  db:
    hosts:
      - name: db-master
        host: 192.168.1.20
        user: dba
        port: 22
        tags: [mysql, primary]
      - name: db-slave
        host: 192.168.1.21
        user: dba
        port: 22
        tags: [mysql, replica]

  cache:
    hosts:
      - name: redis-01
        host: 192.168.1.30
        user: deploy
        tags: [redis]
```

### 5.2 SSH 连接管理

```python
class SSHPool:
    """SSH 连接池，复用连接，避免每次重连。"""

    def __init__(self, max_connections: int = 20):
        self._pool: dict[str, asyncssh.SSHClientConnection] = {}

    async def get(self, host: str, user: str, port: int = 22) -> asyncssh.SSHClientConnection:
        key = f"{user}@{host}:{port}"
        if key not in self._pool or self._pool[key].closed:
            self._pool[key] = await asyncssh.connect(host, port=port, username=user)
        return self._pool[key]

    async def close_all(self):
        for conn in self._pool.values():
            conn.close()
        self._pool.clear()
```

使用 `asyncssh` 库，支持密钥认证和 SSH Agent 转发。

## 6. 交互式 CLI

### 6.1 主界面

```
┌─────────────────────────────────────────────────────────────┐
│  AI Terminal v1.0.0                    集群: web(3) db(2)   │
│  当前用户: deploy@web-01              会话: abc123          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  你> 看看所有服务器的磁盘使用率                               │
│                                                             │
│  [Agent] 正在检查 5 台服务器...                               │
│                                                             │
│  ┌──────────┬────────┬──────────┬──────────┐                │
│  │ 服务器   │ 磁盘   │ 已用     │ 使用率   │                │
│  ├──────────┼────────┼──────────┼──────────┤                │
│  │ web-01   │ /      │ 12G/40G  │ 30% ✓   │                │
│  │ web-02   │ /      │ 35G/40G  │ 88% ⚠   │                │
│  │ web-03   │ /      │ 8G/40G   │ 20% ✓   │                │
│  │ db-master│ /data  │ 180G/200G│ 90% ⚠   │                │
│  │ db-slave │ /data  │ 50G/200G │ 25% ✓   │                │
│  └──────────┴────────┴──────────┴──────────┘                │
│                                                             │
│  [Agent] 警告: web-02 和 db-master 磁盘使用率超过 85%         │
│  建议: 清理 web-02 的 /var/log 和 db-master 的 binlog        │
│                                                             │
│  你> 帮我清理 web-02 的日志                                   │
│                                                             │
│  ┌─────────────────────────────────────────┐                │
│  │  [HIGH] 即将执行                         │                │
│  │  ssh web-02 "find /var/log -name '*.log' │                │
│  │    -mtime +7 -exec rm {} \;"             │                │
│  │                                          │                │
│  │  替代方案: mv 到 /var/trash/              │                │
│  │  [y] 执行  [a] 替代  [e] 编辑  [n] 取消  │                │
│  └─────────────────────────────────────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 会话管理

```python
# 会话持久化 — 支持断线恢复
session = agent.create_session(
    session_id="terminal-main",
    system_prompt="""你是一个专业的终端运维助手。

你的职责：
1. 帮助用户操作终端、管理服务器
2. 在执行危险操作前必须确认
3. 提供清晰的执行结果和建议
4. 主动发现潜在问题

安全规则：
- 删除操作必须使用 mv 到 trash 替代 rm
- 批量操作必须逐台确认
- 所有操作记录审计日志
""",
)
```

### 6.3 快捷命令

| 命令 | 说明 |
|------|------|
| `/status` | 查看集群整体状态 |
| `/logs [host] [keyword]` | 搜索日志 |
| `/deploy [service] [version]` | 部署服务 |
| `/history` | 查看操作历史 |
| `/rollback` | 回滚上一次操作 |
| `/switch [cluster]` | 切换集群上下文 |
| `/confirm` | 确认当前待执行的操作 |
| `/cancel` | 取消当前待执行的操作 |
| `/safe-mode` | 进入安全模式（所有操作都需要确认） |

## 7. 知识库集成

利用 Wuwei 的 RAG 系统，内置运维知识库：

```python
knowledge_store = InMemoryKnowledgeStore(embedder)

# 导入运维手册
await knowledge_store.ingest(nginx_runbook, source="runbooks/nginx.md")
await knowledge_store.ingest(mysql_runbook, source="runbooks/mysql.md")
await knowledge_store.ingest(docker_runbook, source="runbooks/docker.md")

# Agent 遇到问题时自动检索相关手册
agent = Agent(
    llm=llm,
    tools=tools,
    hooks=[
        SafetyHook(safety_policy),                       # 安全审批
        AuditHook(audit_logger),                         # 审计日志
        IncidentLearningHook(llm, skill_generator, memory_store),  # 踩坑自动沉淀为 Skill
        RagRetrievalHook(knowledge_store),               # 自动注入相关运维知识
        MemoryRetrievalHook(memory_store),                # 记住用户偏好和历史决策
        MemoryExtractionHook(llm, memory_store),
    ],
)
```

**知识库内容：**

- 各服务的运维手册（nginx、mysql、redis、docker...）
- 常见故障排查指南
- 公司内部运维规范
- 历史故障案例和解决方案

## 8. 经验沉淀 — 踩坑自动变 Skill

核心想法：每次遇到问题、踩了坑、解决了故障，Agent 自动把经验提炼成可复用的 Skill，下次遇到类似情况直接调用。

### 8.1 什么时候触发沉淀

| 触发场景 | 说明 |
|----------|------|
| 命令执行失败后重试成功 | 第一次方案不行，换个思路才解决 |
| 用户纠正了 Agent 的做法 | "别这样做，应该那样" |
| 手动回滚后恢复 | 操作出了问题，回滚才救回来 |
| 用户主动说"记住这个" | 用户明确要求沉淀 |
| 排查过程超过 3 轮 | 花了不少功夫才定位到问题 |

### 8.2 Skill 生成流程

```
踩坑发生
  → IncidentRecorder 记录完整上下文（命令、错误、排查过程、最终方案）
  → LLM 分析，生成结构化的 Skill 草案
  → 用户确认 / 编辑 / 拒绝
  → 写入 skills/ 目录，成为可复用的 Skill
```

### 8.3 生成的 Skill 长什么样

以 "nginx 502 错误排查" 为例，自动生成的 Skill：

```markdown
---
name: nginx-502-troubleshoot
description: Nginx 502 Bad Gateway 错误排查与修复
tags: [nginx, 502, upstream, troubleshooting]
created_from: incident_20260513_103000
---

# Nginx 502 错误排查

## 触发条件
当用户报告 nginx 返回 502 错误，或日志中出现 "upstream prematurely closed connection"。

## 排查步骤

1. 检查后端服务是否存活
   ```bash
   systemctl status php-fpm   # 或对应的后端服务
   curl -I http://localhost:9000/health
   ```

2. 检查 nginx error log
   ```bash
   tail -50 /var/log/nginx/error.log | grep 502
   ```

3. 检查 PHP-FPM 进程数是否耗尽
   ```bash
   ps aux | grep php-fpm | wc -l
   cat /etc/php-fpm.d/www.conf | grep max_children
   ```

4. 检查 socket 文件是否存在
   ```bash
   ls -la /run/php-fpm/www.sock
   ```

## 修复方案

如果是进程数耗尽：
```bash
# 临时增加
sed -i 's/max_children = 50/max_children = 100/' /etc/php-fpm.d/www.conf
systemctl restart php-fpm
```

如果是 socket 文件丢失：
```bash
systemctl restart php-fpm
```

## 预防措施
- 监控 php-fpm 活跃进程数
- 设置 pm.max_requests 防止内存泄漏
- 配置 nginx upstream 健康检查

## 本次案例
- 时间: 2026-05-13
- 现象: web-02 nginx 502，后端 php-fpm 进程数耗尽
- 根因: 代码内存泄漏导致 php-fpm worker 不释放
- 解决: 增加 max_children + 修复代码内存泄漏
```

### 8.4 核心实现

```python
# ai_terminal/knowledge/incident_recorder.py

@dataclass
class Incident:
    """一次踩坑事件的完整记录。"""
    id: str
    timestamp: datetime
    user_input: str                    # 用户原始描述
    symptoms: list[str]                # 现象描述
    commands_tried: list[CommandStep]  # 尝试过的命令（含成功和失败的）
    root_cause: str                    # 根因分析
    solution: str                      # 最终解决方案
    prevention: list[str]              # 预防措施
    related_hosts: list[str]           # 涉及的主机
    related_services: list[str]        # 涉及的服务
    severity: str                      # low/medium/high/critical
    tags: list[str]                    # 标签

@dataclass
class CommandStep:
    """排查过程中的一步。"""
    command: str
    target: str
    output: str
    exit_code: int
    worked: bool           # 这步是否有效
    insight: str           # 从这步得到的线索
```

```python
# ai_terminal/knowledge/skill_generator.py

class SkillGenerator:
    """从踩坑事件生成 Skill。"""

    GENERATION_PROMPT = """你是一个运维专家。根据以下故障排查过程，生成一个可复用的 Skill。

要求：
1. 写清楚"什么时候用这个 Skill"（触发条件）
2. 列出排查步骤，每步都有具体命令
3. 给出修复方案
4. 提出预防措施
5. 记录本次案例的根因

输出 Markdown 格式，包含 YAML frontmatter。

故障记录：
{incident}

排查过程：
{steps}
"""

    async def generate(self, incident: Incident) -> str:
        """从事件生成 Skill Markdown。"""
        steps_text = "\n".join(
            f"{'✓' if s.worked else '✗'} {s.command} → {s.insight}"
            for s in incident.commands_tried
        )
        prompt = self.GENERATION_PROMPT.format(
            incident=self._format_incident(incident),
            steps=steps_text,
        )
        response = await self.llm.generate([
            Message(role="user", content=prompt)
        ])
        return response.content

    async def save_skill(self, skill_content: str, name: str) -> str:
        """保存 Skill 到文件系统。"""
        skill_dir = Path(f"skills/{name}")
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_content, encoding="utf-8")
        return str(skill_file)
```

```python
# ai_terminal/knowledge/incident_hook.py

class IncidentLearningHook(RuntimeHook):
    """自动检测踩坑并触发 Skill 生成。"""

    def __init__(self, llm, skill_generator: SkillGenerator, memory_store):
        self.llm = llm
        self.generator = skill_generator
        self.memory = memory_store
        # 当前 run 的排查过程
        self._current_steps: list[CommandStep] = []
        self._failure_count = 0

    async def after_tool(self, session, tool_call, tool_message, *, step, task=None, tool=None):
        """记录每一步的执行结果。"""
        if tool_call.function.name not in ("run_command", "ssh_exec", "cluster_exec"):
            return

        result = json.loads(tool_message.content) if tool_message.content else {}
        worked = result.get("ok", False) and result.get("exit_code", -1) == 0

        self._current_steps.append(CommandStep(
            command=tool_call.function.arguments.get("command", ""),
            target=tool_call.function.arguments.get("host", "local"),
            output=result.get("stdout", "")[:500],
            exit_code=result.get("exit_code", -1),
            worked=worked,
            insight="",
        ))

        if not worked:
            self._failure_count += 1

    async def on_run_end(self, session, result, *, task=None):
        """run 结束时判断是否需要沉淀经验。"""
        should_learn = (
            self._failure_count >= 2                    # 失败了 2 次以上
            or self._had_user_correction(session)       # 用户纠正了做法
            or self._long_investigation()               # 排查超过 3 轮
        )

        if not should_learn or not self._current_steps:
            self._reset()
            return

        # 构建事件记录
        incident = Incident(
            id=f"incident_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(timezone.utc),
            user_input=self._get_original_input(session),
            symptoms=self._extract_symptoms(session),
            commands_tried=self._current_steps,
            root_cause="",      # 让 LLM 分析
            solution="",        # 让 LLM 分析
            prevention=[],
            related_hosts=self._get_hosts(),
            related_services=self._get_services(),
            severity="medium",
            tags=[],
        )

        # 生成 Skill
        skill_content = await self.generator.generate(incident)

        # 保存（自动，不需要用户确认，但可以后续编辑）
        skill_name = f"incident-{incident.id}"
        path = await self.generator.save_skill(skill_content, skill_name)

        # 记录到记忆库
        await self.memory.add(
            f"踩坑经验已沉淀为 Skill: {skill_name}，路径: {path}",
            memory_type="summary",
            importance=0.8,
        )

        self._reset()

    def _reset(self):
        self._current_steps.clear()
        self._failure_count = 0
```

### 8.5 Skill 的使用方式

沉淀下来的 Skill 会自动被 SkillHook 加载，Agent 在遇到类似问题时会自动参考：

```
用户: "web-03 的 nginx 报 502 了"

Agent 内部:
  1. SkillHook 注入了可用 Skill 列表到 system prompt
  2. Agent 发现有个 "nginx-502-troubleshoot" Skill
  3. 调用 load_skill 加载详细步骤
  4. 按照 Skill 中的排查步骤逐一执行
  5. 找到根因并修复
```

**Skill 和记忆的区别：**

| | 记忆 (Memory) | Skill |
|--|---------------|-------|
| 内容 | 碎片化信息 | 结构化操作指南 |
| 形式 | "上次用 systemctl restart 解决了" | 完整的排查步骤 + 命令 |
| 用途 | 辅助决策 | 直接指导执行 |
| 来源 | 自动抽取 | 从故障事件生成 |
| 存储 | MemoryStore | skills/ 目录 |

### 8.6 Skill 管理

```bash
# 查看所有沉淀的 Skill
ai-terminal> /skills

# 查看某个 Skill 详情
ai-terminal> /skills nginx-502-troubleshoot

# 编辑 Skill（打开编辑器）
ai-terminal> /skills --edit nginx-502-troubleshoot

# 删除 Skill
ai-terminal> /skills --delete nginx-502-troubleshoot

# 手动触发沉淀当前排查过程
ai-terminal> /learn

# 导入外部运维手册为 Skill
ai-terminal> /skills --import docs/runbook.md
```

## 9. 实现阶段

### Phase 1：本地终端助手（1-2 周）

- [x] 项目初始化
- [ ] 交互式 CLI（基于 prompt_toolkit）
- [ ] 本地 Shell 工具（run_command）
- [ ] 安全策略引擎（命令分级 + 确认流程）
- [ ] 审计日志
- [ ] 基础会话管理

**交付物：** 能用自然语言操作本地终端，危险命令会拦截确认。

### Phase 2：远程服务器（2-3 周）

- [ ] SSH 连接管理（asyncssh）
- [ ] 远程执行工具（ssh_exec）
- [ ] 集群配置（inventory.yaml）
- [ ] 集群批量工具（cluster_exec）
- [ ] 批量操作安全策略

**交付物：** 能管理多台远程服务器，批量操作有安全保护。

### Phase 3：智能运维（2-3 周）

- [ ] 监控诊断工具（system_status, check_logs, check_port）
- [ ] 运维知识库（RAG）
- [ ] 长期记忆（记住用户偏好、历史决策）
- [ ] 自动问题发现和建议
- [ ] 回滚机制

**交付物：** Agent 能主动发现问题、给出建议、查阅运维手册。

### Phase 3.5：经验沉淀（1-2 周）

- [ ] IncidentRecorder — 记录排查过程
- [ ] SkillGenerator — LLM 生成 Skill 草案
- [ ] IncidentLearningHook — 自动检测踩坑并触发沉淀
- [ ] Skill 管理命令（/skills, /learn）
- [ ] Skill 与 RAG 知识库联动

**交付物：** 每次踩坑自动沉淀为可复用的 Skill，下次遇到类似问题直接调用。

### Phase 4：部署流水线（2-3 周）

- [ ] 部署工具（deploy）
- [ ] 滚动更新策略
- [ ] 部署前检查（磁盘、端口、依赖）
- [ ] 部署后验证（健康检查、日志监控）
- [ ] 自动回滚

**交付物：** 支持安全的自动化部署。

### Phase 5：高级功能（持续迭代）

- [ ] Web UI 仪表盘
- [ ] 多用户权限管理
- [ ] 告警集成（Prometheus/Grafana）
- [ ] 自定义工作流（编排复杂操作）
- [ ] 插件系统

## 9. 依赖

```toml
[project]
name = "ai-terminal"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "wuwei>=1.0.0",
    "asyncssh>=2.14",
    "prompt_toolkit>=3.0",
    "rich>=13.0",          # 终端富文本渲染
    "pyyaml>=6.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "black"]
```

## 10. 关键设计决策

**Q: 为什么不直接用 subprocess 而用 asyncssh？**
A: asyncssh 原生异步，支持连接复用、密钥认证、端口转发，比 subprocess + ssh 命令行更可靠。

**Q: 为什么命令分级不用 LLM 判断？**
A: 安全判断不能依赖 LLM（可能误判）。用正则规则 + 白名单/黑名单做确定性判断，LLM 只负责生成命令和提供建议。

**Q: 为什么批量操作默认串行？**
A: 串行方便观察每台的执行结果，发现问题可以立即暂停。并行虽然快但出了问题很难定位和回滚。

**Q: 为什么用 mv 到 trash 替代 rm？**
A: rm 不可逆，mv 到 trash 可以恢复。trash 目录定期清理（默认 7 天），兼顾安全和磁盘空间。
