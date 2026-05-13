# AI Terminal — 交互界面设计

参考 Claude Code / Warp AI / Cursor 的终端交互体验，打造高级感的命令行界面。

> 注意：本文主要保留早期交互设计草案。当前代码已经切换到 `Textual` 全屏 TUI，实际实现以 `ai_terminal/tui/` 和 `ai_terminal/services/` 为准，不再使用 `prompt_toolkit` 作为主界面框架。

## 技术栈

```
prompt_toolkit    — 输入框、补全、快捷键
rich              — 富文本渲染、表格、进度条、Markdown
rich-live         — 实时刷新（流式输出）
rich-panel        — 面板布局
rich-syntax       — 代码高亮
rich.markdown     — Markdown 渲染
```

## 整体布局

```
╭─ AI Terminal ────────────────────────────────────────────────────────╮
│  🟢 connected │ web(3) db(2) │ deploy@web-01 │ session:abc123       │
╰──────────────────────────────────────────────────────────────────────╯

  你> 看看所有服务器的磁盘使用率

  ⏳ 正在检查 5 台服务器...

  ┌ web-01 ──────────────────────────────────┐
  │ Filesystem      Size  Used Avail Use%    │
  │ /dev/sda1        40G   12G   28G  30% ✓  │
  └──────────────────────────────────────────┘

  ┌ web-02 ──────────────────────────────────┐
  │ Filesystem      Size  Used Avail Use%    │
  │ /dev/sda1        40G   35G    5G  88% ⚠  │
  └──────────────────────────────────────────┘

  ┌ web-03 ──────────────────────────────────┐
  │ Filesystem      Size  Used Avail Use%    │
  │ /dev/sda1        40G    8G   32G  20% ✓  │
  └──────────────────────────────────────────┘

  ┌ db-master ───────────────────────────────┐
  │ Filesystem      Size  Used Avail Use%    │
  │ /dev/sdb1       200G  180G   20G  90% ⚠  │
  └──────────────────────────────────────────┘

  ┌ db-slave ────────────────────────────────┐
  │ Filesystem      Size  Used Avail Use%    │
  │ /dev/sdb1       200G   50G  150G  25% ✓  │
  └──────────────────────────────────────────┘

  💡 发现 2 台服务器磁盘使用率超过 85%:
     • web-02: /var/log 占用 15G，建议清理 7 天前的日志
     • db-master: binlog 占用 120G，建议清理过期 binlog

  你> _
```

## 组件设计

### 1. 顶部状态栏

```python
from rich.panel import Panel
from rich.text import Text

class StatusBar:
    """顶部状态栏 — 显示连接状态、集群、当前用户、会话 ID。"""

    def render(self, state: AppState) -> Panel:
        text = Text()
        text.append("  ", style="bold")

        # 连接状态指示灯
        if state.connected:
            text.append("● ", style="bold green")
            text.append("connected", style="green")
        else:
            text.append("● ", style="bold red")
            text.append("disconnected", style="red")

        text.append(" │ ", style="dim")

        # 集群信息
        for cluster, count in state.clusters.items():
            text.append(f"{cluster}({count}) ", style="cyan")

        text.append("│ ", style="dim")

        # 当前用户和主机
        text.append(f"{state.user}@{state.host}", style="yellow")

        text.append("│ ", style="dim")

        # 会话 ID
        text.append(f"session:{state.session_id[:8]}", style="dim")

        return Panel(text, style="blue", height=1)
```

### 2. 输入框

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style

class InputBox:
    """智能输入框 — 支持补全、多行、历史、快捷键。"""

    STYLE = Style.from_dict({
        "prompt": "bold cyan",
        "input": "white",
    })

    def __init__(self):
        # 命令补全器
        self.completer = CommandCompleter([
            "/status", "/logs", "/deploy", "/history",
            "/rollback", "/switch", "/safe-mode", "/skills",
            "/learn", "/clear", "/help", "/exit",
            "看看", "检查", "重启", "部署", "清理",
            "搜索", "查找", "对比", "备份",
        ])

        # Shell 语法高亮
        self.lexer = PygmentsLexer(BashLexer)

        self.session = PromptSession(
            style=self.STYLE,
            completer=self.completer,
            lexer=self.lexer,
            multiline=False,
            wrap_lines=True,
        )

    async def get_input(self) -> str:
        return await self.session.prompt_async(
            [("class:prompt", " 你> ")],
        )
```

**输入框特性：**

- Tab 补全：输入 `/de` 按 Tab → `/deploy`
- 上下箭头：翻阅历史命令
- Ctrl+R：反向搜索历史
- Ctrl+A/E：行首/行尾
- Ctrl+K：删除到行尾
- 多行输入：`\` 续行，或 Shift+Enter 换行

### 3. Agent 输出区域

```python
from rich.live import Live
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table
from rich.panel import Panel

class OutputRenderer:
    """Agent 输出渲染器 — 流式渲染 Markdown、代码、表格、面板。"""

    def __init__(self):
        self.console = Console()
        self.live = None

    async def stream_events(self, events):
        """流式渲染 Agent 事件。"""
        with Live(console=self.console, refresh_per_second=15) as live:
            buffer = ""

            async for event in events:
                if event.type == "text_delta":
                    buffer += event.data["content"]
                    # 实时渲染 Markdown
                    live.update(Markdown(buffer))

                elif event.type == "tool_start":
                    # 显示工具调用开始
                    self._render_tool_start(live, event)

                elif event.type == "tool_end":
                    # 显示工具执行结果
                    self._render_tool_end(live, event)

                elif event.type == "approval_required":
                    # 显示审批请求
                    await self._render_approval(live, event)

                elif event.type == "done":
                    # 显示完成信息（token 用量、耗时）
                    self._render_done(event)

    def _render_tool_start(self, live, event):
        """渲染工具调用开始。"""
        tool_name = event.data["tool_name"]
        args = event.data["args"]

        panel = Panel(
            f"⏳ 执行中: {tool_name}\n参数: {args}",
            title=f"[bold blue]🔧 {tool_name}[/]",
            border_style="blue",
        )
        live.update(panel)

    def _render_tool_end(self, live, event):
        """渲染工具执行结果。"""
        tool_name = event.data["tool_name"]
        output = event.data["output"]
        exit_code = event.data.get("exit_code", 0)

        # 根据 exit_code 选择样式
        if exit_code == 0:
            border_style = "green"
            icon = "✓"
        else:
            border_style = "red"
            icon = "✗"

        # 输出内容高亮
        if self._is_json(output):
            content = Syntax(output, "json", theme="monokai")
        elif self._is_code(output):
            content = Syntax(output, "bash", theme="monokai")
        else:
            content = output

        panel = Panel(
            content,
            title=f"[bold {border_style}]{icon} {tool_name}[/]",
            border_style=border_style,
        )
        live.update(panel)
```

### 4. 工具调用展示

工具调用时显示折叠面板，类似 Claude Code：

```
  🔧 run_command ──────────────────────────────────────────────
  │ 命令: df -h │ 目标: web-01 │ 耗时: 450ms │ ✓ 成功
  ─────────────────────────────────────────────────────────────
  │ Filesystem      Size  Used Avail Use% Mounted on
  │ /dev/sda1        40G   12G   28G  30% /
  │ tmpfs           7.8G     0  7.8G   0% /dev/shm
  ─────────────────────────────────────────────────────────────
```

```python
class ToolCallRenderer:
    """工具调用渲染器 — 可折叠的工具执行面板。"""

    def render(self, tool_call: ToolCallEvent) -> Panel:
        # 头部：工具名 + 元信息
        header = Text()
        header.append(f"  🔧 {tool_call.name}", style="bold cyan")
        header.append(" ──", style="dim")

        # 元信息行
        meta = Text()
        meta.append("  │ ", style="dim")
        meta.append(f"命令: {tool_call.command}", style="white")
        meta.append(" │ ", style="dim")
        meta.append(f"目标: {tool_call.target}", style="yellow")
        meta.append(" │ ", style="dim")
        meta.append(f"耗时: {tool_call.duration_ms}ms", style="dim")
        meta.append(" │ ", style="dim")

        if tool_call.exit_code == 0:
            meta.append("✓ 成功", style="bold green")
        else:
            meta.append(f"✗ 失败 (exit {tool_call.exit_code})", style="bold red")

        # 输出内容
        output = self._format_output(tool_call.output)

        # 组装面板
        content = Text()
        content.append_text(meta)
        content.append("\n  ", style="dim")
        content.append("─" * 50, style="dim")
        content.append("\n")
        content.append(output)
        content.append("\n  ")
        content.append("─" * 50, style="dim")

        return Panel(
            content,
            title=header,
            border_style="green" if tool_call.exit_code == 0 else "red",
            padding=(0, 1),
        )

    def _format_output(self, output: str) -> str:
        """格式化输出：代码高亮、表格渲染、截断长输出。"""
        if len(output) > 2000:
            output = output[:2000] + f"\n  ... (省略 {len(output) - 2000} 字符)"
        return output
```

### 5. 审批确认界面

```
  ┌─ ⚠️  需要确认 ────────────────────────────────────────────┐
  │                                                           │
  │  [HIGH] 删除文件                                          │
  │                                                           │
  │  命令: find /var/log -name "*.log" -mtime +7 -delete      │
  │  目标: web-01                                             │
  │  风险: 删除文件，不可恢复                                  │
  │                                                           │
  │  ┌─ 💡 建议替代方案 ──────────────────────────────────┐   │
  │  │ find /var/log -name "*.log" -mtime +7 \            │   │
  │  │   -exec mv {} /tmp/trash/ \;                       │   │
  │  │ （7 天后自动清理 trash 目录）                        │   │
  │  └────────────────────────────────────────────────────┘   │
  │                                                           │
  │  📋 回滚方案: mv /tmp/trash/*.log /var/log/               │
  │                                                           │
  │  [y] 确认执行  [a] 使用替代方案  [e] 编辑  [n] 取消       │
  │                                                           │
  └───────────────────────────────────────────────────────────┘
```

```python
class ApprovalRenderer:
    """审批确认渲染器。"""

    def render(self, request: ApprovalRequest) -> Panel:
        # 风险等级颜色
        risk_colors = {
            "LOW": "yellow",
            "HIGH": "red",
            "CRITICAL": "bold red",
        }
        risk_color = risk_colors.get(request.risk_level, "white")

        content = Text()

        # 风险等级
        content.append(f"  [{request.risk_level}]", style=risk_color)
        content.append(f" {request.title}\n\n", style="bold")

        # 命令详情
        content.append("  命令: ", style="bold")
        content.append(f"{request.command}\n", style="cyan")
        content.append("  目标: ", style="bold")
        content.append(f"{request.target}\n", style="yellow")
        content.append("  风险: ", style="bold")
        content.append(f"{request.risk_description}\n\n", style=risk_color)

        # 替代方案
        if request.alternative:
            alt_panel = Panel(
                request.alternative,
                title="[bold yellow]💡 建议替代方案[/]",
                border_style="yellow",
            )
            content.append(alt_panel)
            content.append("\n")

        # 回滚方案
        if request.rollback_command:
            content.append("  📋 回滚方案: ", style="bold")
            content.append(f"{request.rollback_command}\n\n", style="dim")

        # 操作按钮
        content.append("  [y] 确认执行", style="bold green")
        content.append("  ", style="dim")
        if request.alternative:
            content.append("[a] 使用替代方案", style="bold yellow")
            content.append("  ", style="dim")
        content.append("[e] 编辑", style="bold cyan")
        content.append("  ", style="dim")
        content.append("[n] 取消", style="bold red")

        return Panel(
            content,
            title="[bold yellow]⚠️  需要确认[/]",
            border_style="yellow",
            padding=(1, 2),
        )
```

### 6. 批量操作进度

```
  ┌─ 🔄 批量操作: systemctl restart nginx ─────────────────────┐
  │                                                             │
  │  web-01  ████████████████████████  ✓ 完成 (1.2s)           │
  │  web-02  ████████████████████████  ✓ 完成 (0.8s)           │
  │  web-03  ████████████░░░░░░░░░░░░  ⏳ 执行中...            │
  │  web-04  ░░░░░░░░░░░░░░░░░░░░░░░░  ⏸ 等待中               │
  │                                                             │
  │  进度: 2/4 完成 │ 成功: 2 │ 失败: 0 │ 耗时: 3.2s           │
  │                                                             │
  │  [p] 暂停  [c] 取消剩余  [s] 跳过当前                       │
  └─────────────────────────────────────────────────────────────┘
```

```python
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

class BatchProgressRenderer:
    """批量操作进度渲染器。"""

    def __init__(self):
        self.results: dict[str, str] = {}  # host -> status

    def render(self, batch: BatchExecution) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 2))

        for host in batch.hosts:
            status = batch.status(host)

            if status == "completed":
                icon = "✓"
                style = "green"
                time_str = f"({batch.duration(host):.1f}s)"
            elif status == "running":
                icon = "⏳"
                style = "yellow"
                time_str = "执行中..."
            elif status == "failed":
                icon = "✗"
                style = "red"
                time_str = f"失败 ({batch.error(host)})"
            else:
                icon = "⏸"
                style = "dim"
                time_str = "等待中"

            # 进度条
            progress = batch.progress(host)
            bar = "█" * int(progress * 20) + "░" * (20 - int(progress * 20))

            table.add_row(
                Text(host, style="bold"),
                Text(f"  {bar}", style=style),
                Text(f"  {icon} {time_str}", style=style),
            )

        # 底部统计
        stats = Text()
        stats.append(f"\n  进度: {batch.completed}/{batch.total} 完成", style="bold")
        stats.append(f" │ 成功: {batch.success}", style="green")
        stats.append(f" │ 失败: {batch.failed}", style="red" if batch.failed > 0 else "dim")
        stats.append(f" │ 耗时: {batch.total_time:.1f}s", style="dim")

        content = Group(table, stats)

        return Panel(
            content,
            title=f"[bold blue]🔄 批量操作: {batch.command}[/]",
            border_style="blue",
            padding=(1, 1),
        )
```

### 7. 智能提示

Agent 执行完毕后，根据结果显示上下文相关的操作建议：

```
  💡 你可以:
     • 清理 web-02 的日志: find /var/log -name "*.log" -mtime +7 -delete
     • 清理 db-master 的 binlog: PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 7 DAY)
     • 查看详细磁盘分析: du -sh /var/log/*
     • 设置磁盘告警: /alert disk > 85%
```

```python
class SuggestionRenderer:
    """智能提示渲染器 — 根据上下文建议下一步操作。"""

    def render(self, suggestions: list[str]) -> Text:
        text = Text()
        text.append("\n  💡 你可以:\n", style="bold yellow")

        for i, suggestion in enumerate(suggestions, 1):
            text.append(f"     • {suggestion}\n", style="cyan")

        return text
```

### 8. 错误展示

```
  ┌─ ❌ 执行失败 ──────────────────────────────────────────────┐
  │                                                             │
  │  命令: systemctl restart nginx                              │
  │  目标: web-03                                               │
  │  错误: Job for nginx.service failed because a timeout       │
  │        was exceeded.                                        │
  │                                                             │
  │  ┌─ 🔍 可能原因 ──────────────────────────────────────┐    │
  │  │ 1. 配置文件语法错误                                  │    │
  │  │ 2. 端口 80 被其他进程占用                             │    │
  │  │ 3. SSL 证书路径不存在                                 │    │
  │  └────────────────────────────────────────────────────┘    │
  │                                                             │
  │  🔧 建议操作:                                               │
  │     nginx -t               检查配置语法                     │
  │     lsof -i :80            检查端口占用                     │
  │     journalctl -u nginx    查看详细日志                     │
  │                                                             │
  │  [r] 重试  [d] 诊断  [s] 跳过  [b] 回滚                    │
  └─────────────────────────────────────────────────────────────┘
```

## 输入模式

用户输入有三种模式，自动识别，无需手动切换：

### 模式一：直接执行命令（`!` 前缀）

输入 `!` 开头 → 直接作为 Shell 命令执行，不经过 AI。

```
  你> !ls -la
  total 48
  drwxr-xr-x 5 user user 4096 May 13 10:30 .
  drwxr-xr-x 3 user user 4096 May 10 09:00 ..
  -rw-r--r-- 1 user user  220 May 10 09:00 .bashrc

  你> !ssh web-01 "systemctl status nginx"
  ● nginx.service - A high performance web server
     Active: active (running) since Mon 2026-05-12 09:00:00 CST

  你> !docker ps
  CONTAINER ID   IMAGE     STATUS       PORTS
  a1b2c3d4e5f6   nginx     Up 2 hours   0.0.0.0:80->80/tcp
```

**特点：**
- 和普通终端完全一样，直接执行
- 支持管道、重定向、后台运行
- 输出原样显示，不做 Markdown 渲染
- 仍然受安全策略约束（HIGH/CRITICAL 仍需确认）
- 记录到审计日志

### 模式二：自然语言对话（默认）

不带前缀 → 走 AI Agent，自然语言理解 + 工具调用。

```
  你> 看看所有服务器的磁盘使用率

  ⏳ 正在检查 5 台服务器...
  [Agent 输出 Markdown 表格]

  你> 帮我把 web-02 的日志清理一下

  ⚠️  需要确认...
```

### 模式三：混合模式（`>` 前缀）

输入 `>` 开头 → 先用 AI 理解意图，但不自动执行，而是生成命令让你确认。

```
  你> > 清理 7 天前的日志

  🤖 我理解你的意图，生成以下命令:

     find /var/log -name "*.log" -mtime +7 -delete

  [y] 执行  [e] 编辑  [n] 取消

  你> e

  📝 编辑命令:
  > find /var/log -name "*.log" -mtime +7 -exec mv {} /tmp/trash/ \;

  [y] 执行  [n] 取消
```

**特点：**
- AI 帮你翻译自然语言为命令
- 但不自动执行，先给你看
- 可以编辑后再执行
- 适合不确定 AI 会执行什么的时候

### 自动识别规则

```python
def detect_input_mode(user_input: str) -> InputMode:
    """自动识别输入模式。"""
    text = user_input.strip()

    # 模式一：直接命令
    if text.startswith("!"):
        return InputMode.DIRECT_COMMAND, text[1:]

    # 模式三：混合模式
    if text.startswith(">"):
        return InputMode.HYBRID, text[1:]

    # 模式二：自然语言（默认）
    return InputMode.AI_CHAT, text
```

### Shell 环境继承

直接命令模式（`!`）继承当前 Shell 环境：

```python
class DirectCommandExecutor:
    """直接命令执行器 — 不经过 AI，直接执行。"""

    def __init__(self):
        # 继承当前 Shell 的环境变量
        self.env = os.environ.copy()
        # 当前工作目录
        self.cwd = os.getcwd()
        # 命令历史（与 shell history 共享）
        self.history = self._load_shell_history()

    async def execute(self, command: str) -> CommandResult:
        """直接执行命令。"""
        # 支持 cd 切换目录（持久化）
        if command.strip().startswith("cd "):
            target = command.strip()[3:].strip()
            new_cwd = os.path.expanduser(target)
            if os.path.isdir(new_cwd):
                self.cwd = os.path.abspath(new_cwd)
                return CommandResult(ok=True, output=f"cd {self.cwd}")
            else:
                return CommandResult(ok=False, error=f"目录不存在: {target}")

        # 支持 export 设置环境变量（持久化）
        if command.strip().startswith("export "):
            var_def = command.strip()[7:].strip()
            key, _, value = var_def.partition("=")
            self.env[key.strip()] = value.strip().strip('"').strip("'")
            return CommandResult(ok=True, output=f"export {key.strip()}={value.strip()}")

        # 正常执行
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=self.env,
        )
        stdout, stderr = await proc.communicate()

        return CommandResult(
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            exit_code=proc.returncode,
        )
```

### 输入框提示符变化

不同模式下提示符颜色不同，让用户知道自己在哪个模式：

```
  你> ls -la                    # 白色 → AI 对话模式
  !> ls -la                     # 绿色 → 直接命令模式
  >> 清理日志                   # 黄色 → 混合模式
```

```python
def get_prompt(mode: InputMode) -> list[tuple[str, str]]:
    """根据模式返回提示符样式。"""
    if mode == InputMode.DIRECT_COMMAND:
        return [("class:prompt-direct", " !> ")]      # 绿色
    elif mode == InputMode.HYBRID:
        return [("class:prompt-hybrid", " >> ")]       # 黄色
    else:
        return [("class:prompt", " 你> ")]              # 白色
```

### 使用场景对比

| 场景 | 推荐模式 | 示例 |
|------|----------|------|
| 快速执行已知命令 | `!` 直接执行 | `!docker ps` |
| 复杂运维任务 | AI 对话 | "帮我排查 web-02 的 502 错误" |
| 不确定命令怎么写 | `>` 混合模式 | "> 查看端口占用" |
| 管道组合 | `!` 直接执行 | `!ps aux \| grep nginx` |
| 批量操作 | AI 对话 | "重启所有 Web 服务器" |
| 学习命令 | `>` 混合模式 | "> 怎么查看 TCP 连接数" |

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Tab` | 命令补全 |
| `↑/↓` | 历史命令 |
| `Ctrl+R` | 反向搜索历史 |
| `Ctrl+C` | 中断当前操作 |
| `Ctrl+D` | 退出 |
| `Ctrl+L` | 清屏 |
| `Ctrl+A` | 行首 |
| `Ctrl+E` | 行尾 |
| `Ctrl+K` | 删除到行尾 |
| `Ctrl+U` | 删除到行首 |
| `Ctrl+W` | 删除前一个词 |
| `Esc` | 取消当前审批 |
| `F1` | 帮助 |
| `F2` | 切换集群 |
| `F3` | 安全模式开关 |
| `!!` | 重复上一条直接命令 |
| `!n` | 执行历史中第 n 条命令 |

## 主题配置

`~/.ai-terminal/theme.yaml`：

```yaml
theme: dark    # dark / light / auto

colors:
  primary: cyan
  success: green
  warning: yellow
  danger: red
  info: blue
  dim: gray

layout:
  show_status_bar: true
  show_tool_details: true
  compact_mode: false       # 紧凑模式（减少空行）
  max_output_lines: 100     # 单个工具最大输出行数
  auto_scroll: true         # 自动滚动到底部

animations:
  typing_effect: true       # 打字机效果
  progress_bars: true       # 进度条动画
  spinner_style: dots       # dots / line / arrow / bounce
```

## 会话界面

### 历史会话

```
  ┌─ 📋 会话历史 ──────────────────────────────────────────────┐
  │                                                             │
  │  abc123  2026-05-13 10:30  "磁盘清理"     12 条消息  3 次操作│
  │  def456  2026-05-12 15:00  "nginx 502 排查" 28 条消息  8 次操作│
  │  ghi789  2026-05-11 09:00  "部署 v2.1"    45 条消息 15 次操作│
  │                                                             │
  │  [Enter] 恢复会话  [d] 删除  [e] 导出  [n] 新建              │
  └─────────────────────────────────────────────────────────────┘
```

### 操作历史

```
  ┌─ 📜 操作历史 (今天) ───────────────────────────────────────┐
  │                                                             │
  │  10:30  ✓  df -h                    web-01     450ms        │
  │  10:31  ✓  df -h                    web-02     380ms        │
  │  10:31  ✓  df -h                    web-03     420ms        │
  │  10:32  ⚠  find /var/log ...delete  web-01     用户取消     │
  │  10:33  ✓  mv /var/log/*.log ...    web-01     1.2s         │
  │  10:35  ✓  systemctl restart nginx  web-01     2.1s         │
  │  10:35  ✓  systemctl restart nginx  web-02     1.8s         │
  │  10:36  ✗  systemctl restart nginx  web-03     超时         │
  │  10:37  ✓  nginx -t                 web-03     0.3s         │
  │  10:38  ✓  systemctl restart nginx  web-03     3.2s         │
  │                                                             │
  │  [↑↓] 浏览  [Enter] 重执行  [r] 回滚  [f] 筛选              │
  └─────────────────────────────────────────────────────────────┘
```

## 实现代码

### 主应用入口

```python
# ai_terminal/app.py

import asyncio
from prompt_toolkit import PromptSession
from rich.console import Console
from rich.live import Live
from wuwei import Agent, LLMGateway, ToolRegistry

class AITerminal:
    """AI 终端管家主应用。"""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.console = Console()
        self.renderer = OutputRenderer(self.console)
        self.input_box = InputBox()
        self.session = agent.create_session(session_id="terminal-main")
        self.state = AppState()

    async def run(self):
        """主循环。"""
        self._print_banner()

        while True:
            try:
                # 获取用户输入（提示符随模式变化）
                user_input = await self.input_box.get_input()

                if not user_input.strip():
                    continue

                # 处理快捷命令
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                    continue

                # 自动识别输入模式
                mode, text = detect_input_mode(user_input)

                if mode == InputMode.DIRECT_COMMAND:
                    # 直接执行 Shell 命令，不经过 AI
                    await self._exec_direct(text)

                elif mode == InputMode.HYBRID:
                    # AI 理解意图 → 生成命令 → 用户确认 → 执行
                    await self._exec_hybrid(text)

                else:
                    # 自然语言对话
                    await self._exec_ai(text)

            except KeyboardInterrupt:
                self.console.print("\n  [dim]Ctrl+C 中断[/dim]")
                continue
            except EOFError:
                self.console.print("\n  [dim]再见！[/dim]")
                break

    async def _exec_direct(self, command: str):
        """直接执行 Shell 命令。"""
        # 安全检查（即使是直接命令也要过安全策略）
        risk = self.safety_policy.classify(command)
        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            if not await self._confirm(command, risk):
                return

        # 执行
        result = await self.direct_executor.execute(command)

        # 渲染输出（原样显示，不做 Markdown 渲染）
        if result.stdout:
            self.console.print(result.stdout, end="")
        if result.stderr:
            self.console.print(result.stderr, style="red", end="")

        # 记录审计日志
        self.audit_logger.log(command=command, target="local", result=result)

    async def _exec_hybrid(self, text: str):
        """混合模式：AI 生成命令，用户确认后执行。"""
        # 让 AI 理解意图并生成命令
        prompt = f"根据以下需求生成一条 shell 命令，只输出命令本身，不要解释：\n{text}"
        response = await self.agent.run(prompt, session=self.session)
        generated_command = response.content.strip().strip("`")

        # 显示生成的命令，让用户确认
        self.console.print(f"\n  🤖 生成命令:\n")
        self.console.print(f"     {generated_command}", style="bold cyan")

        # 确认/编辑/取消
        action = await self._prompt_action(["y", "e", "n"], default="n")

        if action == "y":
            # 直接执行
            await self._exec_direct(generated_command)
        elif action == "e":
            # 编辑后执行
            edited = await self.input_box.get_input(
                prompt="📝 编辑命令: ", default=generated_command
            )
            if edited.strip():
                await self._exec_direct(edited)
        # action == "n": 取消

    async def _exec_ai(self, text: str):
        """自然语言对话。"""
        events = self.agent.stream_events(text, session=self.session)
        await self.renderer.stream_events(events)

    def _print_banner(self):
        """打印启动横幅。"""
        banner = """
  ╔═══════════════════════════════════════════════════════╗
  ║                                                       ║
  ║   🖥️  AI Terminal v1.0.0                              ║
  ║   智能终端管家 — 用自然语言操作终端、管理集群          ║
  ║                                                       ║
  ║   你>   自然语言对话       "看看磁盘使用率"            ║
  ║   !>    直接执行命令       "!docker ps"                ║
  ║   >>    AI 生成命令确认    "> 清理日志"                 ║
  ║   /     快捷命令           "/help" "/status"           ║
  ║                                                       ║
  ╚═══════════════════════════════════════════════════════╝
        """
        self.console.print(banner, style="bold cyan")

    async def _handle_command(self, cmd: str):
        """处理快捷命令。"""
        parts = cmd.strip().split()
        command = parts[0]

        handlers = {
            "/status": self._cmd_status,
            "/logs": self._cmd_logs,
            "/history": self._cmd_history,
            "/skills": self._cmd_skills,
            "/learn": self._cmd_learn,
            "/safe-mode": self._cmd_safe_mode,
            "/clear": self._cmd_clear,
            "/help": self._cmd_help,
            "/exit": self._cmd_exit,
        }

        handler = handlers.get(command)
        if handler:
            await handler(parts[1:])
        else:
            self.console.print(f"  [red]未知命令: {command}[/red]")
            self.console.print("  [dim]输入 /help 查看可用命令[/dim]")


async def main():
    """应用入口。"""
    from ai_terminal.config import load_config
    from ai_terminal.safety import SafetyPolicy, SafetyHook
    from ai_terminal.cluster import ClusterManager
    from ai_terminal.tools import register_all_tools

    config = load_config()

    # 初始化集群管理器
    cluster = ClusterManager(config["inventory"])

    # 初始化工具
    registry = ToolRegistry()
    register_all_tools(registry, cluster_manager=cluster)

    # 初始化 LLM
    llm = LLMGateway.from_env()

    # 初始化 Agent
    agent = Agent(
        llm=llm,
        tools=registry,
        hooks=[
            SafetyHook(SafetyPolicy(config["safety"])),
            AuditHook(config["audit_dir"]),
            IncidentLearningHook(llm, ...),
            RagRetrievalHook(...),
            MemoryRetrievalHook(...),
            MemoryExtractionHook(llm, ...),
            ConsoleHook(),
        ],
    )

    # 启动应用
    app = AITerminal(agent)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
```

## 效果对比

| 特性 | 普通终端 | AI Terminal |
|------|----------|-------------|
| 输入 | 纯文本 | 补全 + 高亮 + 历史搜索 |
| 输出 | 纯文本 | Markdown + 代码高亮 + 表格 |
| 工具调用 | 看不到 | 可折叠面板 + 耗时 + 状态 |
| 批量操作 | 逐个手动 | 进度条 + 实时状态 |
| 错误处理 | 看错误码 | 智能诊断 + 建议操作 |
| 审批 | 无 | 可视化确认 + 替代方案 |
| 历史 | shell history | 完整操作记录 + 回滚 |
