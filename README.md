# AI Terminal

智能终端管家 — 用自然语言操作终端、管理集群。

基于 [Wuwei](https://github.com/xiaojiaenen/wuwei) Agent 框架构建。

## 功能

- **自然语言操作终端** — 描述需求，AI 生成并执行命令
- **多服务器集群管理** — SSH 远程执行，支持并行操作
- **安全策略** — 命令四级分类 + 确认流程 + 审计日志
- **踩坑自动沉淀** — 失败命令自动诊断根因，生成可复用 Skill
- **运维知识库（RAG）** — 导入文档，语义搜索
- **高级交互** — Rich 美化输出、prompt_toolkit 自动补全

## 安装

```bash
pip install -e .
```

或使用 uv：

```bash
uv pip install -e .
```

## 使用

```bash
# 交互模式
ai-terminal

# 单次执行
ai-terminal "docker ps"
```

## 输入模式

| 前缀 | 模式 | 示例 |
|------|------|------|
| 无 | AI 对话 | "看看磁盘使用率" |
| `!` | 直接执行 | `!docker ps` |
| `>` | 混合模式 | "> 清理日志" |
| `/` | 快捷命令 | `/status` |

## 快捷命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/status` | 系统状态 |
| `/history` | 执行历史 |
| `/stats` | 审计统计 |
| `/config` | 当前配置 |
| `/incidents` | 踩坑记录 |
| `/hosts` | 主机清单 |
| `/quit` | 退出 |

## 安全策略

命令分为四个风险等级：

| 等级 | 说明 | 处理方式 |
|------|------|----------|
| SAFE | 只读命令（ls、cat、grep） | 自动执行 |
| LOW | 可逆写入（mkdir、cp、git commit） | 自动执行 |
| HIGH | 破坏性命令（rm、docker rm） | 需确认，推荐替代方案 |
| CRITICAL | 不可逆破坏（rm -rf /、DROP DATABASE） | 二次确认 |

## 配置

配置文件位置：`~/.ai-terminal/config.yaml`

```yaml
general:
  default_target: local
  language: zh-CN

safety:
  enabled: true
  trash_dir: ~/.ai-terminal/trash
  command_timeout: 30
  whitelist: []
  blacklist: []

llm:
  provider: openai
  model: gpt-4o
  temperature: 0.1

cluster:
  inventory_file: ~/.ai-terminal/inventory.yaml
  connection_timeout: 10
```

## 集群管理

主机清单文件：`~/.ai-terminal/inventory.yaml`

```yaml
hosts:
  - name: web-1
    hostname: 192.168.1.10
    port: 22
    user: root
    tags: [web, production]

  - name: db-1
    hostname: 192.168.1.20
    port: 22
    user: root
    tags: [database, production]

groups:
  production: [web-1, db-1]
  web: [web-1]
```

## 踩坑自动诊断

内置 13 种常见错误模式自动诊断：

- `Permission denied` → 权限不足
- `command not found` → 命令未安装
- `port already in use` → 端口被占用
- `No space left on device` → 磁盘空间不足
- `Connection refused` → 连接被拒绝
- `ModuleNotFoundError` → Python 模块缺失
- ...

失败命令自动记录，支持搜索和生成 Skill 文档。

## 项目结构

```
ai_terminal/
├── __init__.py
├── app.py              # CLI 主应用
├── agent.py            # LLM Agent 集成
├── config.py           # 配置管理
├── safety/
│   ├── policy.py       # 安全策略引擎
│   └── audit.py        # 审计日志
├── tools/
│   └── shell_tools.py  # 本地 Shell 工具
├── cluster/
│   └── remote.py       # SSH 远程执行
├── runtime/
│   ├── safety_hook.py  # 安全审批 Hook
│   └── incident.py     # 踩坑自动沉淀
├── knowledge/
│   └── knowledge_tools.py  # 运维知识库 RAG
└── ui/
    ├── components.py   # Rich UI 组件
    └── prompt.py       # prompt_toolkit 交互
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check ai_terminal/
black ai_terminal/
```

## License

Apache-2.0
