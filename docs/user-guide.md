# AI Terminal 用户操作手册

## 目录

- [1. 简介](#1-简介)
- [2. 安装与启动](#2-安装与启动)
- [3. 三种输入模式](#3-三种输入模式)
- [4. 快捷命令](#4-快捷命令)
- [5. 配置文件](#5-配置文件)
- [6. 安全策略](#6-安全策略)
- [7. 远程集群管理](#7-远程集群管理)
- [8. 历史与审计](#8-历史与审计)
- [9. 知识库](#9-知识库)
- [10. 踩坑记录](#10-踩坑记录)
- [11. 数据存储说明](#11-数据存储说明)
- [12. 常见问题](#12-常见问题)

---

## 1. 简介

AI Terminal 是一款基于 AI 的智能终端管家。你可以用自然语言描述需求，AI 自动生成并执行命令，支持 Windows / Linux / macOS 三平台。

**核心能力：**
- 自然语言 → 命令执行
- 4 级安全策略自动审批
- 多台远程服务器批量管理
- 命令失败自动诊断根因
- 知识库 RAG 检索

---

## 2. 安装与启动

### 方式一：下载可执行文件（推荐，无需 Python）

从 [GitHub Releases](https://github.com/xiaojiaenen/AITerminal/releases) 下载对应平台版本：

| 平台 | 文件名 |
|------|--------|
| Windows x64 | `ai-terminal-windows-x64.exe` |
| Linux x64 | `ai-terminal-linux-x64` |
| macOS Intel | `ai-terminal-macos-x64` |
| macOS Apple Silicon | `ai-terminal-macos-arm64` |

下载后直接运行即可。

### 方式二：pip 安装（需要 Python 3.10+）

```bash
pip install ai-terminal
```

### 启动

```bash
# 交互模式（默认）
ai-terminal

# 指定配置文件
ai-terminal -c /path/to/config.yaml

# 单次执行后退出
ai-terminal "echo hello"

# 设置命令超时（秒）
ai-terminal -t 60

# 查看帮助
ai-terminal --help
```

### 配置 LLM API Key

交互模式需要大模型 API。创建 `~/.ai-terminal/config.yaml`：

```yaml
llm:
  provider: openai
  model: deepseek-v4-pro        # 或 gpt-4o / claude-sonnet-4-6 等
  api_key: sk-your-api-key
  base_url: https://api.deepseek.com   # DeepSeek 需设置，OpenAI 可省略
  temperature: 0.1
  max_tokens: 4096
```

也可通过环境变量：`export OPENAI_API_KEY=sk-xxx`

---

## 3. 三种输入模式

| 输入方式 | 模式 | 说明 | 示例 |
|----------|------|------|------|
| 无前缀 | AI 对话 | AI 理解需求，调用工具执行 | `看看磁盘使用率` |
| `!` 前缀 | 直接执行 | 跳过 AI，直接运行命令 | `!df -h` |
| `>` 前缀 | 混合模式 | AI 生成命令，人工确认后执行 | `> 清理 Docker 日志` |

### AI 对话模式（默认）

直接输入自然语言，AI 会：
1. 分析你的需求
2. 调用安全检查工具评估命令
3. 执行只读命令（自动放行）
4. 高风险命令弹出确认

```
用户: 看看系统内存使用情况
AI: [执行 free -h] ... 总内存 16G，可用 8.2G
```

### 直接执行模式（`!`）

跳过 AI，直接执行命令，但仍经过安全策略检查。

```
!docker ps
!ls -la /var/log
```

### 混合模式（`>`）

AI 先生成命令，展示给你确认，再决定是否执行。

```
> 找出占用 CPU 最高的 3 个进程
AI 建议: ps aux --sort=-%cpu | head -4
确认执行？(y/N/edit):
```

- `y` — 执行
- `N` — 取消
- `edit` — 修改命令后再执行

---

## 4. 快捷命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/status` | 显示系统状态（工作目录、超时、安全策略、主机数） |
| `/history` | 最近 20 条执行记录 |
| `/stats` | 审计统计 + 踩坑统计 |
| `/config` | 当前配置树 |
| `/incidents` | 查看踩坑记录 |
| `/hosts` | 显示主机清单 |
| `/quit` 或 `/exit` | 退出 |

---

## 5. 配置文件

### 配置查找顺序

1. `~/.ai-terminal/config.yaml`（优先）
2. `~/.ai-terminal/config.yml`
3. `./ai-terminal.yaml`（当前目录）
4. `./ai-terminal.yml`

命令行 `-c` 参数可以覆盖以上所有路径。

### 环境变量覆盖

任何配置项都可以通过环境变量 `AI_TERMINAL_` 前缀覆盖：

```bash
export AI_TERMINAL_SAFETY_COMMAND_TIMEOUT=60
export AI_TERMINAL_LLM_MODEL=gpt-4o
```

点号分隔的路径用下划线替代：`safety.command_timeout` → `AI_TERMINAL_SAFETY_COMMAND_TIMEOUT`。

### 完整配置示例

```yaml
general:
  default_target: local
  language: zh-CN
  history_file: ~/.ai-terminal/history
  max_history: 1000

safety:
  enabled: true
  trash_dir: ~/.ai-terminal/trash
  trash_retention_days: 7
  require_confirmation: true
  max_batch_size: 5
  command_timeout: 30
  whitelist:              # 白名单命令（直接放行）
    - "echo hello"
  blacklist:              # 黑名单命令（直接拒绝）
    - "rm -rf /"
  # custom_rules:         # 自定义规则
  #   - pattern: "^my-deploy\\b"
  #     level: critical

audit:
  enabled: true
  log_dir: ~/.ai-terminal/audit

llm:
  provider: openai
  model: deepseek-v4-pro
  temperature: 0.1
  max_tokens: 4096
  api_key: sk-xxx
  base_url: https://api.deepseek.com

cluster:
  inventory_file: ~/.ai-terminal/inventory.yaml
  connection_timeout: 10
  command_timeout: 60

knowledge:
  enabled: true
  store_path: ~/.ai-terminal/knowledge
```

---

## 6. 安全策略

### 风险等级

| 等级 | 颜色 | 说明 | 行为 |
|------|------|------|------|
| SAFE | 绿色 | 只读操作，无副作用 | 自动执行 |
| LOW | 蓝色 | 低风险操作 | 自动执行 |
| HIGH | 黄色 | 破坏性操作 | 需用户确认 |
| CRITICAL | 红色 | 不可逆高危操作 | 需用户确认 + 提供回滚方案 |

### 示例

| 命令 | Windows | Linux/macOS | 风险 |
|------|---------|-------------|------|
| `dir` / `ls` | SAFE | SAFE | 只读 |
| `type` / `cat` | SAFE | SAFE | 只读 |
| `echo hello` | SAFE | SAFE | 只读 |
| `del file` / `rm file` | HIGH | HIGH | 删除文件 |
| `rm -rf /` | CRITICAL | CRITICAL | 不可逆 |
| `git push --force` | HIGH | HIGH | 覆盖远程 |
| `docker rm` | HIGH | HIGH | 删除容器 |

### 安全建议机制

高风险命令会提供安全替代方案和回滚命令。例如 `rm -rf /tmp/cache` 会建议先备份或使用回收站。

---

## 7. 远程集群管理

### 主机清单

创建 `~/.ai-terminal/inventory.yaml`：

```yaml
hosts:
  - name: web-01
    hostname: 192.168.1.10
    port: 22
    user: root
    key_file: ~/.ssh/id_rsa
    tags: [web, production]

  - name: db-01
    hostname: 192.168.1.20
    port: 22
    user: admin
    password: your-password   # 或使用 key_file
    tags: [database, production]

groups:
  web: [web-01]
  database: [db-01]
  all: [web-01, db-01]
```

### 使用方式

在 AI 对话模式中直接描述需求：

```
在所有 web 服务器上查看 nginx 状态
查看 db-01 的磁盘使用率
```

AI 会自动调用 `remote_run` 工具在对应主机上执行命令。

---

## 8. 历史与审计

### 查看历史

```
/history   # 最近 20 条记录
/stats     # 统计信息
```

显示字段：
- 时间
- 操作（已执行 / 已确认 / 已拒绝 / 已拦截）
- 风险等级
- 目标主机
- 命令（截断到 50 字符）

### 审计日志文件

所有操作记录在 `~/.ai-terminal/audit/` 目录：

```
~/.ai-terminal/audit/
├── audit-2026-05-13.jsonl    # 每天一个文件
├── audit-2026-05-12.jsonl
└── audit-2026-05-11.jsonl
```

格式：JSONL（每行一条 JSON），包含完整的命令和输出。

---

## 9. 知识库

AI 可以记住你教它的运维知识，下次对话自动检索。

### 摄入知识

```
把 nginx 重启流程记下来：先检查配置 nginx -t，再 systemctl reload nginx
记住：生产环境数据库密码在 /etc/secrets/db_password
```

### 检索知识

AI 对话时会自动搜索相关知识，也可以手动查：

```
怎么重启 nginx？
```

### 存储说明

知识库当前存储在内存中，**重启后清空**。后续版本会支持持久化。

---

## 10. 踩坑记录

命令执行失败时，AI 会自动诊断并记录根因。

### 自动诊断

支持的 13 种错误模式：
- `Permission denied` — 权限不足
- `command not found` — 命令未安装
- `No such file or directory` — 路径不存在
- `port already in use` — 端口占用
- `No space left on device` — 磁盘满
- `Connection refused / timed out` — 连接失败
- `ModuleNotFoundError` — Python 模块缺失
- 等等...

### 查看记录

```
/incidents   # 最近 10 条
```

### 生成 Skill

成功解决后可从踩坑记录生成可复用的操作 Skill。

---

## 11. 数据存储说明

### 存储总览

| 数据 | 格式 | 位置 | 持久化 | 备注 |
|------|------|------|--------|------|
| 配置文件 | YAML | `~/.ai-terminal/config.yaml` | 是 | |
| 主机清单 | YAML | `~/.ai-terminal/inventory.yaml` | 是 | |
| 审计日志 | JSONL | `~/.ai-terminal/audit/audit-{date}.jsonl` | 是 | 每天一个文件 |
| 踩坑记录 | JSONL | `~/.ai-terminal/incidents/incidents.jsonl` | 是 | |
| Skill 文件 | Markdown | `~/.ai-terminal/incidents/skills/*.md` | 是 | |
| 对话上下文 | 内存 | 无 | 否 | 每次 `agent.run()` 最多 10 轮 |
| 知识库 | 内存 | `~/.ai-terminal/knowledge/` | 否 | store_path 参数未生效 |

### 数据截断规则

| 数据 | 截断长度 |
|------|----------|
| 审计日志 output 字段 | 1000 字符 |
| 踩坑记录 error_output 字段 | 2000 字符 |
| 历史显示命令字段 | 50 字符 |
| 知识库分块 | 500 字符/块 |

### 对话历史生命周期

- AI Terminal 的对话上下文**不落盘**，仅存在内存中
- 每次 `agent.run()` 最多 10 轮工具调用（`max_steps=10`）
- 退出程序后对话历史清空
- wuwei 框架内置了 `ContextCompressionHook`（上下文压缩）和 `StorageHook`（会话持久化），当前版本未启用，后续可按需开启

---

## 12. 常见问题

### Q: 为什么 AI 对话不工作？

检查 `~/.ai-terminal/config.yaml` 中的 `llm.api_key` 是否正确，或环境变量 `OPENAI_API_KEY` 是否设置。

### Q: 中文输出乱码？

Windows 下已自动强制 UTF-8 输出。如果仍然乱码，确认终端支持 UTF-8（推荐 Windows Terminal）。

### Q: 如何跳过安全确认？

- 将命令加入白名单（`safety.whitelist`）
- 或使用低风险命令（只读操作自动放行）

### Q: 远程执行需要什么条件？

需要目标服务器开启 SSH，配置好密钥或密码，并在 `inventory.yaml` 中正确填写。

### Q: 退出时的错误信息？

已自动抑制 asyncio 子进程清理时的 ResourceWarning，不影响正常使用。

### Q: 打包体积为什么这么大？

24.5MB 是因为打包了 Python 运行时和全部依赖（wuwei + asyncssh + prompt_toolkit + rich + pydantic 等）。
