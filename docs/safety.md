# AI Terminal — 安全设计

安全是这个项目的第一优先级。本文档详细说明安全机制的实现。

## 核心原则

1. **默认安全** — 未明确放行的操作一律拦截
2. **最小权限** — Agent 只拥有完成任务所需的最小权限
3. **可逆优先** — 能用可逆操作替代的，绝不用不可逆操作
4. **全程审计** — 所有操作记录日志，不可篡改
5. **人工兜底** — 关键操作必须人类确认，不依赖 AI 判断安全性

## 1. 命令安全分类

### 1.1 分类规则

命令安全分类用**正则规则**判断，不用 LLM。原因：安全判断必须是确定性的，LLM 可能误判。

```python
# SAFE — 只读，没有任何副作用
SAFE_COMMANDS = {
    # 文件查看
    r"^ls\b", r"^cat\b", r"^head\b", r"^tail\b", r"^less\b", r"^more\b",
    r"^file\b", r"^stat\b", r"^wc\b", r"^du\b", r"^df\b",
    r"^find\b(?!.*-delete)(?!.*-exec\s+rm)",  # find 不带 -delete
    # 搜索
    r"^grep\b", r"^rg\b", r"^ag\b", r"^awk\b(?!.*>)", r"^sed\b(?!.*-i)",
    # 系统信息
    r"^ps\b", r"^top\b", r"^htop\b", r"^free\b", r"^uptime\b",
    r"^whoami\b", r"^id\b", r"^hostname\b", r"^uname\b",
    r"^ip\b", r"^ifconfig\b", r"^netstat\b", r"^ss\b",
    r"^lsof\b", r"^mount\b", r"^lsblk\b", r"^lscpu\b",
    # 网络（只读）
    r"^ping\b", r"^traceroute\b", r"^nslookup\b", r"^dig\b",
    r"^curl\b(?!.*-X\s*(POST|PUT|DELETE|PATCH))",  # curl GET 请求
    r"^wget\b(?!.*-O\s*/)",  # wget 不覆盖系统文件
    # Docker（只读）
    r"^docker ps\b", r"^docker images\b", r"^docker logs\b",
    r"^docker inspect\b", r"^docker stats\b", r"^docker top\b",
    # Git（只读）
    r"^git (status|log|diff|show|branch|remote)\b",
    # Systemd（只读）
    r"^systemctl status\b", r"^systemctl is-active\b",
    r"^systemctl list-units\b", r"^journalctl\b",
}

# LOW — 写入操作，但可逆或影响范围小
LOW_COMMANDS = {
    # 文件创建/复制
    r"^touch\b", r"^mkdir\b", r"^cp\b", r"^mv\b",
    r"^ln\b", r"^install\b",
    r"^echo\b.*>>",  # 追加写入
    r"^tee\b.*-a",   # tee 追加
    r"^sed\s+-i\b",  # sed 原地编辑（可从备份恢复）
    r"^tar\b.*-x",   # 解压
    r"^unzip\b",
    # Docker（创建/启停）
    r"^docker run\b", r"^docker start\b", r"^docker stop\b",
    r"^docker compose\b(.*up|.*down|.*restart)",
    # Git（提交/推送）
    r"^git (add|commit|push|pull|fetch|checkout|branch|merge|stash)\b",
    # 包管理
    r"^pip(3?)\s+install\b", r"^npm\s+install\b", r"^apt\s+install\b",
    r"^yum\s+install\b", r"^brew\s+install\b",
    # 系统服务（启停）
    r"^systemctl (start|restart|reload)\b",
}

# HIGH — 破坏性操作，有备份路径但需要确认
HIGH_COMMANDS = {
    # 文件删除
    r"^rm\b", r"^rmdir\b", r"^shred\b",
    r"^find\b.*-delete", r"^find\b.*-exec\s+rm",
    # 覆盖写入
    r"^echo\b.*>[^>]", r"^tee\b(?!.*-a)",  # 覆盖（非追加）
    r"^cp\b.*/dev/null",  # 清空文件
    # Docker（删除）
    r"^docker rm\b", r"^docker kill\b", r"^docker rmi\b",
    r"^docker compose\b.*rm",
    # Git（破坏性）
    r"^git reset\b.*--hard", r"^git clean\b.*-f",
    r"^git push\b.*--force", r"^git branch\b.*-D",
    # 系统管理
    r"^systemctl (stop|disable|mask)\b",
    r"^iptables\b", r"^ufw\b",
    r"^userdel\b", r"^groupdel\b",
    r"^crontab\b.*-r",  # 删除 crontab
    # 数据库
    r"^mysql\b.*-e.*DELETE\b", r"^mysql\b.*-e.*DROP\b",
    r"^redis-cli\b.*FLUSH",
}

# CRITICAL — 不可逆，可能造成系统级破坏
CRITICAL_COMMANDS = {
    r"^rm\s+(-rf?|--recursive)\s*/",       # 根目录递归删除
    r"^rm\s+(-rf?|--recursive)\s+~",       # 家目录递归删除
    r"^rm\s+(-rf?|--recursive)\s+\*",      # 通配符递归删除
    r"^mkfs\b",                             # 格式化
    r"^dd\b.*of=/dev/",                     # dd 写磁盘
    r"^fdisk\b", r"^parted\b",              # 分区操作
    r"^shutdown\b", r"^reboot\b", r"^halt\b", r"^poweroff\b",
    r"^init\s+[06]",                        # 关机/重启
    r"^DROP\s+DATABASE\b",                  # SQL 删除数据库
    r"^TRUNCATE\b",                         # SQL 清空表
    r"^docker system prune\b.*-a",          # 清理所有 Docker
    r"^docker volume rm\b",                 # 删除 Docker 卷
    r"^>\s*/dev/sd",                        # 直接写磁盘设备
    r"^chmod\s+(-R\s+)?777\s+/",            # 根目录全开权限
    r"^chown\s+(-R\s+)?",                   # 修改所有者（可能破坏权限）
}
```

### 1.2 分类优先级

从高到低匹配，一旦命中即返回：

```
CRITICAL > HIGH > LOW > SAFE
```

如果所有规则都不匹配，默认归为 **HIGH**（未知命令视为危险）。

### 1.3 自定义规则

用户可以在 `~/.ai-terminal/safety.yaml` 中自定义规则：

```yaml
# 强制放行（跳过所有检查）
whitelist:
  - "^my-deploy-script"    # 内部部署脚本信任

# 强制拦截（直接拒绝）
blacklist:
  - "^rm\s+-rf\s+/home/shared"  # 共享目录绝对不能删

# 自定义分级
custom_rules:
  - pattern: "^kubectl delete"
    level: HIGH
    message: "删除 K8s 资源需要确认"
```

## 2. 确认流程

### 2.1 确认界面

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  [HIGH] 需要确认                                            │
│                                                             │
│  命令: rm /var/log/nginx/access.log                         │
│  目标: 本地                                                 │
│  风险: 删除文件，不可恢复                                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  建议替代方案:                                       │    │
│  │  mv /var/log/nginx/access.log /tmp/trash/            │    │
│  │  （7 天后自动清理 trash 目录）                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  回滚方案: mv /tmp/trash/access.log /var/log/nginx/         │
│                                                             │
│  [y] 确认执行    [a] 使用替代方案                           │
│  [e] 编辑命令    [p] 仅预览不执行                           │
│  [n] 取消                                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 CRITICAL 二次确认

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  [CRITICAL] 极高风险操作                                     │
│                                                             │
│  命令: docker system prune -a                               │
│  影响: 删除所有未使用的 Docker 镜像、容器、网络、卷           │
│  此操作不可逆                                                │
│                                                             │
│  请输入 "yes" 确认执行，或其他操作:                          │
│                                                             │
│  > _                                                        │
│                                                             │
│  [n] 取消                                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 批量操作确认

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  [BATCH] 批量操作 — 3 台服务器                               │
│                                                             │
│  命令: systemctl restart nginx                              │
│                                                             │
│  ┌──────────┬───────────────────────┬────────┐              │
│  │ 目标     │ 命令                  │ 风险   │              │
│  ├──────────┼───────────────────────┼────────┤              │
│  │ web-01   │ systemctl restart nginx│ LOW    │              │
│  │ web-02   │ systemctl restart nginx│ LOW    │              │
│  │ web-03   │ systemctl restart nginx│ LOW    │              │
│  └──────────┴───────────────────────┴────────┘              │
│                                                             │
│  执行策略: 逐台执行，间隔 5 秒                               │
│  失败策略: 暂停等待指示                                      │
│                                                             │
│  [y] 全部执行    [s] 逐台确认                               │
│  [n] 取消                                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 3. 沙箱执行

### 3.1 本地命令沙箱

```python
class CommandSandbox:
    """本地命令的安全执行环境。"""

    def __init__(self, config: dict):
        # 限制命令执行时间
        self.timeout = config.get("timeout", 30)
        # 限制输出大小（防止刷屏）
        self.max_output_chars = config.get("max_output_chars", 50_000)
        # 限制工作目录
        self.allowed_cwd = config.get("allowed_cwd", None)  # None = 不限制
        # 禁止的环境变量
        self.blocked_env_vars = {"AWS_SECRET_ACCESS_KEY", "DB_PASSWORD", "API_KEY"}

    async def execute(self, command: str, cwd: str | None = None) -> CommandResult:
        """
        执行命令，返回:
        - stdout: str
        - stderr: str
        - exit_code: int
        - duration_ms: int
        - timed_out: bool
        - truncated: bool  (输出是否被截断)
        """
        # 清理环境变量（移除敏感信息）
        env = {k: v for k, v in os.environ.items() if k not in self.blocked_env_vars}

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return CommandResult(timed_out=True, ...)

        return CommandResult(
            stdout=self._truncate(stdout.decode()),
            stderr=self._truncate(stderr.decode()),
            exit_code=proc.returncode,
            ...
        )
```

### 3.2 远程命令沙箱

SSH 执行时额外的保护：

```python
class RemoteSandbox:
    """远程命令的安全执行环境。"""

    # 禁止在远程执行的命令模式
    BLOCKED_PATTERNS = [
        r"curl.*\|.*sh",        # 禁止管道执行远程脚本
        r"wget.*\|.*sh",
        r"bash\s*<\s*\(",       # 禁止进程替换
        r"eval\s*\(",           # 禁止 eval
        r"exec\s+[0-9]*<>/dev/tcp",  # 禁止反向 shell
    ]

    async def execute(self, ssh_conn, command: str) -> CommandResult:
        # 检查是否包含危险模式
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command):
                return CommandResult(
                    blocked=True,
                    reason=f"命令包含危险模式: {pattern}",
                )

        # 包装命令：限制资源使用
        wrapped = f"timeout {self.timeout} bash -c {shlex.quote(command)}"
        ...
```

## 4. 回滚机制

### 4.1 自动备份

HIGH 级别操作前自动备份相关状态：

```python
class RollbackManager:
    """操作回滚管理。"""

    async def prepare_rollback(self, command: str, target: str) -> RollbackPlan:
        """
        根据命令类型准备回滚方案。

        命令类型 → 回滚策略:
        - rm file → 事先 mv 到 trash，回滚时 mv 回来
        - systemctl stop → 回滚: systemctl start
        - docker rm → 回滚: 用保存的参数 docker run
        - git reset --hard → 回滚: git reflog + git reset
        - iptables -F → 回滚: 从备份恢复 /etc/iptables.rules
        """
        ...

    async def execute_rollback(self, plan: RollbackPlan) -> bool:
        """执行回滚，返回是否成功。"""
        ...
```

### 4.2 Trash 目录

```python
TRASH_DIR = "~/.ai-terminal/trash"

async def safe_delete(path: str, target: str = "local") -> str:
    """
    安全删除：mv 到 trash 而不是 rm。

    返回:
    - trash_path: str  (trash 中的路径，用于回滚)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_path = f"{TRASH_DIR}/{timestamp}_{os.path.basename(path)}"

    if target == "local":
        await run_command(f"mkdir -p {TRASH_DIR} && mv {path} {trash_path}")
    else:
        await ssh_exec(target, f"mkdir -p {TRASH_DIR} && mv {path} {trash_path}")

    return trash_path
```

### 4.3 Trash 自动清理

```yaml
# ~/.ai-terminal/config.yaml
trash:
  auto_cleanup: true
  retention_days: 7      # 7 天后自动清理
  max_size_mb: 1024      # 超过 1G 时按时间清理最旧的
```

## 5. 审计日志

### 5.1 日志格式

每条操作记录为一行 JSON：

```json
{
  "id": "op_20260513_103000_abc123",
  "timestamp": "2026-05-13T10:30:00.123Z",
  "session_id": "sess_xyz",
  "user_input": "重启 nginx",
  "ai_reasoning": "用户要求重启 nginx，执行 systemctl restart nginx",
  "command": "systemctl restart nginx",
  "target": "web-01",
  "target_type": "remote",
  "risk_level": "LOW",
  "decision": "approved",
  "confirmation_type": "auto",
  "output": "Restarting nginx... OK",
  "exit_code": 0,
  "duration_ms": 1234,
  "rollback_command": "systemctl start nginx",
  "rollback_prepared": true,
  "error": null
}
```

### 5.2 日志存储

```
~/.ai-terminal/
├── audit/
│   ├── 2026-05-13.jsonl    # 按天分文件
│   ├── 2026-05-14.jsonl
│   └── ...
├── trash/
│   ├── 20260513_103000_access.log
│   └── ...
├── inventory.yaml           # 集群配置
├── safety.yaml              # 安全策略配置
└── config.yaml              # 全局配置
```

### 5.3 日志查询

```bash
# 查看今天的操作
ai-terminal> /history

# 查看某台机器的操作
ai-terminal> /history --host web-01

# 查看所有 HIGH/CRITICAL 操作
ai-terminal> /history --risk high,critical

# 查看失败的操作
ai-terminal> /history --status failed
```

## 6. 安全模式

### 6.1 普通模式 vs 安全模式

| 行为 | 普通模式 | 安全模式 |
|------|----------|----------|
| SAFE 命令 | 自动执行 | 自动执行 |
| LOW 命令 | 自动执行 | 需确认 |
| HIGH 命令 | 需确认 | 需确认 + 二次确认 |
| CRITICAL 命令 | 需确认 + 二次确认 | 禁止执行 |

### 6.2 切换

```
ai-terminal> /safe-mode on
已进入安全模式。所有写入操作都需要确认。

ai-terminal> /safe-mode off
已退出安全模式。
```

## 7. 敏感信息保护

### 7.1 环境变量过滤

执行命令时自动移除敏感环境变量：

```python
BLOCKED_ENV_VARS = {
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "DB_PASSWORD", "DATABASE_URL", "MYSQL_PWD",
    "API_KEY", "SECRET_KEY", "TOKEN",
    "GITHUB_TOKEN", "GITLAB_TOKEN",
    "DOCKER_PASSWORD", "NPM_TOKEN",
    "PRIVATE_KEY", "SSH_KEY",
}
```

### 7.2 输出脱敏

命令输出中如果包含敏感信息（密码、token 等），自动脱敏：

```python
SENSITIVE_PATTERNS = [
    (r'(password|passwd|pwd)\s*[=:]\s*\S+', r'\1=***'),
    (r'(token|secret|key)\s*[=:]\s*\S+', r'\1=***'),
    (r'sk-[a-zA-Z0-9]{20,}', 'sk-***'),  # API keys
    (r'-----BEGIN.*PRIVATE KEY-----', '[PRIVATE KEY REDACTED]'),
]
```

## 8. 实现清单

```python
# 需要实现的核心类

class SafetyPolicy:        # 命令分级 + 决策
class CommandSandbox:      # 本地安全执行
class RemoteSandbox:       # 远程安全执行
class RollbackManager:     # 回滚准备和执行
class AuditLogger:         # 审计日志记录
class TrashManager:        # 安全删除 + trash 管理
class SensitiveFilter:     # 输出脱敏
class SafetyHook(RuntimeHook):  # Wuwei Hook 集成
class AuditHook(RuntimeHook):   # Wuwei Hook 集成
```
