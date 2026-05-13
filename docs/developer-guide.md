# AI Terminal 开发手册

> 当前主线代码以 `Textual` TUI 为准。本文中出现的旧 `ui/`、`prompt_toolkit` 结构属于历史设计，阅读时请优先对照 `ai_terminal/tui/`、`ai_terminal/services/` 与 `ai_terminal/app.py`。

## 目录

- [1. 项目架构](#1-项目架构)
- [2. 环境搭建](#2-环境搭建)
- [3. 模块详解](#3-模块详解)
- [4. 数据流](#4-数据流)
- [5. 安全策略扩展](#5-安全策略扩展)
- [6. 添加自定义工具](#6-添加自定义工具)
- [7. Hook 系统](#7-hook-系统)
- [8. 上下文与记忆](#8-上下文与记忆)
- [9. 打包发布](#9-打包发布)
- [10. 存储架构详解](#10-存储架构详解)

---

## 1. 项目架构

```
ai_terminal/
├── __init__.py
├── __main__.py              # python -m ai_terminal 入口
├── app.py                   # Textual TUI 入口转发
├── agent.py                 # LLM Agent 集成（封装 wuwei Agent）
├── config.py                # 配置管理（YAML + 环境变量覆盖）
├── cluster/
│   ├── __init__.py
│   └── remote.py            # SSH 远程执行器（基于 asyncssh）
├── knowledge/
│   ├── __init__.py
│   └── knowledge_tools.py   # 运维知识库（JSONL + RAG 工具）
├── runtime/
│   ├── __init__.py
│   ├── incident.py          # 踩坑记录、自动诊断、Skill 生成
│   └── safety_hook.py       # wuwei RuntimeHook — 工具执行前安全拦截
├── safety/
│   ├── __init__.py
│   ├── audit.py             # 审计日志（JSONL 按天轮转）
│   └── policy.py            # 安全策略（4 级正则分类）
├── services/
│   ├── __init__.py
│   └── terminal_service.py  # TUI 服务层
├── skill/
│   ├── __init__.py
│   └── skill_runner.py      # Skill 聚合与检索
├── tools/
│   ├── __init__.py
│   └── shell_tools.py       # 本地命令执行器（跨平台 PowerShell/bash）
└── tui/
    ├── __init__.py
    ├── app.py               # Textual 全屏工作台
    ├── commands.py          # Slash 命令路由
    ├── controllers/         # Chat / Command 工作流控制器
    ├── widgets/             # 输入框、风险确认弹窗等
    └── formatters.py        # 表格与时间线展示辅助
```

### 依赖关系

```
app.py (CLI 入口)
├── agent.py (LLM Agent)
│   └── wuwei (Agent 框架)
│       ├── Agent / AgentRunner (执行循环)
│       ├── LLMGateway (模型调用)
│       ├── ToolRegistry (工具注册)
│       ├── Context (消息容器)
│       └── Hook 系统
├── safety/policy.py (安全策略)
├── safety/audit.py (审计日志)
├── cluster/remote.py (远程执行)
├── tools/shell_tools.py (本地执行)
├── runtime/incident.py (踩坑记录)
├── knowledge/knowledge_tools.py (知识库)
└── ui/ (终端界面)
```

### 核心循环（wuwei Agent）

```
用户输入
  → Agent.run()
    → AgentRunner._run_non_stream()
      → loop (最多 max_steps=10 轮):
          1. HookManager.before_llm(messages, tools)   # 上下文裁剪、注入记忆
          2. LLMGateway.generate(messages, tools)       # 调用模型
          3. HookManager.after_llm(response)
          4. 如果有 tool_calls:
               HookManager.before_tool(tool_call)       # 安全检查
               ToolExecutor.execute_one(tool_call)       # 执行工具
               HookManager.after_tool(tool_call, result) # 持久化结果
          5. 否则: 返回最终结果
```

---

## 2. 环境搭建

### 前置条件

- Python >= 3.10
- Git

### 克隆并安装

```bash
git clone https://github.com/xiaojiaenen/AITerminal.git
cd AITerminal

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装开发依赖
pip install -e ".[dev]"
```

### 配置 LLM

```bash
cp config/config.example.yaml ~/.ai-terminal/config.yaml
# 编辑 config.yaml，填写 api_key
```

### 启动开发

```bash
python -m ai_terminal     # 交互模式
python -m ai_terminal --help
```

### 运行测试

```bash
pytest tests/ -v
```

---

## 3. 模块详解

### 3.1 app.py — 主应用

`AITerminal` 类是命令行交互循环的核心。关键方法：

| 方法 | 说明 |
|------|------|
| `run()` | 交互主循环，打印 Banner、读取输入、路由到三种模式 |
| `handle_ai_chat()` | AI 对话模式，流式输出 + Rich Markdown 渲染 |
| `execute_direct()` | 直接执行模式，带安全检查和确认 |
| `execute_hybrid()` | 混合模式，AI 生成命令 → 确认 → 执行 |
| `handle_command()` | 快捷命令处理（/help, /history 等） |

输入路由逻辑（`detect_mode`）：
```python
"!command" → MODE_DIRECT   (直接执行)
">描述"    → MODE_HYBRID    (混合模式)
其他       → MODE_AI        (AI 对话)
```

### 3.2 agent.py — LLM Agent

`AITerminalAgent` 封装 wuwei 框架：

- `_build_agent()` — 构建 Agent：创建 LLMGateway → 注册工具 → 创建 Agent
- `chat()` — 非流式对话
- `chat_stream()` — 流式对话，返回 `text_delta` 事件
- `generate_command()` — 混合模式，创建无工具 Agent 仅生成命令

系统提示词是平台感知的（Windows / Linux 分别给出不同命令示例）。

### 3.3 safety/policy.py — 安全策略

跨平台 4 级命令分类，使用正则模式匹配：

```python
# 模式组织
_SAFE_UNIX / _SAFE_WINDOWS      # 只读命令
_LOW_UNIX / _LOW_WINDOWS         # 低风险
_HIGH_UNIX / _HIGH_WINDOWS       # 破坏性
_CRITICAL_UNIX / _CRITICAL_WINDOWS  # 不可逆
```

匹配顺序：自定义规则 → 白名单 → CRITICAL → HIGH → SAFE → LOW

添加新模式：

```python
# 在 policy.py 对应列表中添加
_SAFE_WINDOWS: list[re.Pattern] = [
    ...
    re.compile(r"^my-safe-cmd\b", re.IGNORECASE),
]
```

### 3.4 safety/audit.py — 审计日志

- **格式**：JSONL，每天一个文件 `audit-{YYYY-MM-DD}.jsonl`
- **字段**：timestamp, command, action, risk_level, target, exit_code, output, duration_ms
- **截断**：output 截断到 1000 字符
- **查询**：`get_recent(count)` 读当天文件，`get_stats()` 统计

### 3.5 tools/shell_tools.py — 本地执行

跨平台 shell 执行：

- Windows：检测 `pwsh`（PowerShell 7）或回退到 `powershell`，强制 UTF-8 编码
- Linux/macOS：原生 shell 执行

核心方法：
- `ShellExecutor.run(command)` — 执行单条命令，返回 `ShellResult`
- `run_batch(commands, parallel)` — 批量执行
- `run_pipeline(commands)` — 管道执行

### 3.6 cluster/remote.py — 远程执行

基于 asyncssh 的 SSH 远程执行：

- `RemoteExecutor.run_on_hosts(hosts, command)` — 在多个主机上执行
- 支持密钥和密码认证
- 主机清单从 `~/.ai-terminal/inventory.yaml` 加载

### 3.7 runtime/incident.py — 踩坑记录

命令执行失败时自动诊断：

- 13 种已知错误模式的正则匹配
- 从错误输出提取文件名、端口、模块名等具体参数
- 生成 Markdown Skill 文件到 `~/.ai-terminal/incidents/skills/`
- 持久化到 JSONL

### 3.8 knowledge/knowledge_tools.py — 知识库

封装 wuwei `InMemoryKnowledgeStore`：
- `SimpleEmbedder`（bigram hash，256 维，无外部依赖）
- 分块大小 500 字符，重叠 50 字符
- 注册为 3 个 LLM 工具：`ingest_knowledge`, `search_knowledge`, `knowledge_stats`

### 3.9 tui/ — Textual 终端界面

- `app.py`：全屏工作台，管理标签页、输入路由、命令面板和快捷键
- `controllers/`：拆分 AI 对话流和命令执行流
- `widgets/command_input.py`：底部输入栏，负责历史与补全
- `widgets/risk_modal.py`：高风险命令确认弹窗
- `formatters.py`：表格、事件时间线和空状态格式化

---

## 4. 数据流

### 一次 AI 对话的完整流程

```
1. 用户输入 "看看磁盘使用率"
2. app.handle_ai_chat("看看磁盘使用率")
3. agent.chat_stream("看看磁盘使用率")
   ├── agent._build_agent() 创建 wuwei Agent
   ├── agent.stream_events() 流式调用
   │   ├── LLM Gateway 调用 DeepSeek API
   │   ├── LLM 返回 tool_call: run_command("df -h")
   │   ├── HookManager.before_tool() → 安全检查（SAFE，放行）
   │   ├── ShellExecutor.run("df -h") → ShellResult
   │   ├── HookManager.after_tool() → 记录审计日志
   │   ├── 结果回传 LLM
   │   └── LLM 返回最终回复 "磁盘使用率 45%..."
   └── yield text_delta events
4. Rich Live Markdown 实时渲染流式输出
5. 完成
```

### 直接执行模式流程

```
1. 用户输入 "!df -h"
2. detect_mode() → (MODE_DIRECT, "df -h")
3. app.execute_direct("df -h")
   ├── policy.check("df -h") → SAFE，自动放行
   ├── shell.run("df -h") → ShellResult
   ├── print_command_result() 显示输出
   ├── audit.log_execution() 记录日志
   └── 如果失败 → incident.record() 自动诊断
4. 回到交互循环
```

---

## 5. 安全策略扩展

### 添加自定义规则

在 `config.yaml` 中：

```yaml
safety:
  custom_rules:
    - pattern: "^my-deploy\\b"
      level: critical
    - pattern: "^my-safe-backup\\b"
      level: safe
```

### 添加命令白名单/黑名单

```yaml
safety:
  whitelist:
    - "specific-command arg1"
  blacklist:
    - "dangerous-command"
```

### 添加安全替代方案

在 `policy.py` 的 `_WINDOWS_ALTERNATIVES` 或 `_UNIX_ALTERNATIVES` 中添加：

```python
_WINDOWS_ALTERNATIVES = {
    re.compile(r"^my-rm\\b", re.IGNORECASE): ("用回收站代替", "Move-Item {target} $env:TEMP"),
}
```

---

## 6. 添加自定义工具

### 注册新工具到 Agent

在 `agent.py` 的 `_register_safety_tools` 方法后，使用 wuwei 的 `@registry.tool` 装饰器：

```python
@self.registry.tool(
    name="my_tool",
    description="我的自定义工具，做某件事",
)
async def my_tool(param: str) -> dict:
    # 工具逻辑
    return {"result": f"处理了 {param}"}
```

### 访问 Shell 执行器

工具函数内部可访问 `self.shell`（本地）和 `self.remote`（远程）：

```python
@self.registry.tool(
    name="check_status",
    description="检查服务状态",
)
async def check_status(service_name: str, host: str = "local") -> dict:
    if host == "local":
        result = await self.shell.run(f"systemctl status {service_name}")
    else:
        # 远程执行
        ...
    return result.to_dict()
```

---

## 7. Hook 系统

wuwei 的 Hook 系统允许在 Agent 生命周期的关键点注入自定义逻辑。当前 AI-Terminal 已实现 `SafetyApprovalHook`（执行前安全确认）。

### 创建自定义 Hook

```python
from wuwei.runtime.hook import RuntimeHook

class MyHook(RuntimeHook):
    """在执行前后注入逻辑。"""

    async def before_llm(self, session, messages, tools, *, step, task=None):
        """修改发送给 LLM 的消息列表或工具列表。"""
        # 例如：注入当前系统信息
        messages.insert(1, {"role": "system", "content": f"当前时间: {now()}"})
        return messages, tools

    async def after_tool(self, session, tool_call, tool_message, *, step, task=None, tool=None):
        """工具执行后的副作用。"""
        # 例如：发送通知
        print(f"工具 {tool_call.name} 执行完毕")
```

### 注册到 Agent

在 `AITerminalAgent._build_agent()` 中：

```python
self._agent = Agent(
    llm=self._llm,
    tools=self.registry,
    default_system_prompt=SYSTEM_PROMPT,
    default_max_steps=10,
    hooks=[MyHook()],          # 添加自定义 Hook
)
```

### 可用的 Hook 回调

| 回调 | 时机 | 返回值 |
|------|------|--------|
| `before_llm()` | LLM 调用前 | (messages, tools) |
| `after_llm()` | LLM 返回后 | response |
| `before_tool()` | 工具执行前 | (tool_call, continue_flag) |
| `after_tool()` | 工具执行后 | None |
| `before_loop()` | 每轮循环前 | (continue_flag, extra_context) |
| `after_loop()` | 每轮循环后 | None |

---

## 8. 上下文与记忆

### 当前状态

AI-Terminal 的对话上下文**不持久化**：

- 对话历史存储在 wuwei `Context` 对象中（纯内存 `list[Message]`）
- 每次 `agent.run()` 最多 10 轮工具调用
- 程序退出后清空

### 可开启的能力（wuwei 框架内置）

#### 会话持久化（StorageHook）

持久化每次对话到磁盘：

```python
from wuwei.runtime.storage_hook import StorageHook
from wuwei.memory.storage import FileStorage

storage = FileStorage(".wuwei_sessions")
agent = Agent(llm=llm, tools=tools, hooks=[StorageHook(storage)])
```

存储格式：
```
.wuwei_sessions/
├── {session_id}.meta.json   # 会话元数据
└── {session_id}.jsonl       # 消息流
```

#### 上下文压缩（ContextCompressionHook）

当对话超过 N 轮时自动用 LLM 生成摘要：

```python
from wuwei.runtime.context_hook import ContextCompressionHook

agent = Agent(
    llm=llm, tools=tools,
    hooks=[ContextCompressionHook(compress_after_turns=30, keep_recent_turns=5)]
)
```

#### 长期记忆（MemoryRetrievalHook）

记住跨会话的重要信息：

```python
from wuwei.runtime.memory_hook import MemoryRetrievalHook, MemoryExtractionHook
from wuwei.memory.memory_store import InMemoryMemoryStore

store = InMemoryMemoryStore()
agent = Agent(
    llm=llm, tools=tools,
    hooks=[
        MemoryRetrievalHook(store, top_k=5),     # LLM 调用前注入相关记忆
        MemoryExtractionHook(store, llm),         # 对话结束后提取新记忆
    ]
)
```

#### RAG 检索（RagRetrievalHook）

对话时自动检索知识库：

```python
from wuwei.runtime.rag_hook import RagRetrievalHook

agent = Agent(
    llm=llm, tools=tools,
    hooks=[RagRetrievalHook(knowledge_store, top_k=3)]
)
```

### 为什么当前没开启

- 保持简单：当前每个 `agent.run()` 独立执行，不跨会话共享状态
- 安全考虑：敏感命令和输出不落盘
- 后续版本会按需开放这些能力

---

## 9. 打包发布

### 本地打包

```bash
python build.py
```

输出到 `dist/ai-terminal{exe}`。

### CI 自动打包

推送 tag 自动触发 GitHub Actions 四平台构建：

```bash
git tag v0.3.0
git push origin v0.3.0
```

产物在 [GitHub Actions](https://github.com/xiaojiaenen/AITerminal/actions) 下载。

### 减少包体积

`build.py` 已排除以下大型模块（不影响功能）：

```
tkinter, matplotlib, numpy, pandas, PIL, cv2, torch, tensorflow,
onnxruntime, pypdf, pypdfium2, pdfplumber, openpyxl, pptx,
magika, lxml, mammoth, markitdown, speech_recognition, pydub
```

当前 Windows exe 约 24.5MB。

---

## 10. 存储架构详解

### 审计日志（`safety/audit.py`）

```
audit.py:24-48   AuditEntry 数据类
audit.py:50-74   AuditLogger.__init__()  创建按天轮转的 FileHandler
audit.py:99      output[:1000] 截断
audit.py:125-141 get_recent() 读取当天 JSONL
```

- 格式：每行一个 JSON 对象
- 轮转：每天新文件
- 输出截断：1000 字符

### 踩坑记录（`runtime/incident.py`）

```
incident.py:13-26   Incident 数据类
incident.py:59-142  IncidentRecorder + 13 种错误模式
incident.py:150-162 _load() 初始化时读取全部
incident.py:164-168 _save() 追加写入（非原子）
incident.py:203     error_output[:2000] 截断
```

- 文件：`~/.ai-terminal/incidents/incidents.jsonl`
- 写入：直接追加（非原子）
- Skill：Markdown 输出到 `~/.ai-terminal/incidents/skills/`

### 配置（`config.py`）

```
config.py:14-51    _DEFAULT_CONFIG 硬编码默认值
config.py:121-143  Config.__init__() 三层加载
config.py:152-159  _merge() 深度合并
config.py:172-184  _apply_env() AI_TERMINAL_ 前缀覆盖
```

加载顺序：默认值 → YAML 文件 → 环境变量

### 知识库（`knowledge/knowledge_tools.py`）

```
knowledge_tools.py:30-88   OpsKnowledgeBase
knowledge_tools.py:90-170  register_knowledge_tools()
```

- 存储：JSONL 持久化到 `knowledge.store_path`（目录会自动落到 `knowledge.jsonl`）
- 嵌入：`SimpleEmbedder`（bigram hash，256 维）
- 分块：500 字符/块，50 字符重叠

### 对话上下文（wuwei `memory/context.py`）

```
context.py:1-73    Context 类（内存中的消息列表）
context_window.py  SimpleContextWindow（截断 + 摘要）
context_hook.py    ContextCompressionHook（LLM 压缩）
storage.py:33-91   FileStorage（会话持久化）
storage_hook.py    StorageHook（自动保存/加载）
```

当前 AI-Terminal 仅使用基础 `Context`，未启用上述高级特性。

---

## 附录

### 关键文件索引

| 文件 | 行数 | 职责 |
|------|------|------|
| `app.py` | ~374 | CLI 入口、交互循环 |
| `agent.py` | ~240 | LLM Agent 封装 |
| `safety/policy.py` | ~550 | 安全策略引擎 |
| `safety/audit.py` | ~160 | 审计日志 |
| `tools/shell_tools.py` | ~212 | 本地命令执行 |
| `cluster/remote.py` | ~250 | SSH 远程执行 |
| `runtime/incident.py` | ~361 | 踩坑记录 |
| `knowledge/knowledge_tools.py` | ~170 | 知识库 |
| `ui/components.py` | ~200 | Rich UI 组件 |
| `ui/prompt.py` | ~180 | prompt_toolkit 输入 |
| `config.py` | ~230 | 配置管理 |

### wuwei 框架关键文件

| 文件 | 职责 |
|------|------|
| `agent/agent.py` | Agent 门面类 |
| `agent/session.py` | AgentSession 数据类 |
| `runtime/runner.py` | AgentRunner 执行循环 |
| `runtime/hook.py` | Hook 基类 + HookManager |
| `memory/context.py` | Context 消息容器 |
| `memory/context_window.py` | 上下文截断 |
| `memory/context_compressor.py` | LLM 上下文压缩 |
| `memory/storage.py` | FileStorage 会话持久化 |
| `memory/memory_store.py` | 长期记忆存储 |
| `memory/knowledge_store.py` | RAG 知识存储 |
| `memory/embedder.py` | 文本嵌入器 |
| `llm/gateway.py` | LLM 调用网关 |
| `tools/registry.py` | 工具注册表 |
| `tools/executor.py` | 工具执行器 |
