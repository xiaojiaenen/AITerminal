# AI Terminal — 工具清单

本文档列出所有 Agent 可用的工具，包括参数、安全等级和使用场景。

## 当前状态说明

当前代码实际注册的工具以 `ai_terminal/agent.py` 为准，已接入的运行时工具包括：

- `run_command` / `run_pipeline` / `run_batch`
- `remote_run` / `remote_upload` / `list_hosts`
- `check_safety`
- `ingest_knowledge` / `search_knowledge` / `knowledge_stats`
- `record_incident` / `search_incidents` / `get_incident_stats`
- `list_skills` / `search_skills` / `get_skill`

下文中未出现在上述列表里的工具，属于设计稿或规划项，不代表当前版本已经实现或注册。

## 1. 本地 Shell 工具

### run_command

本地执行 Shell 命令。

| 属性 | 值 |
|------|-----|
| 安全等级 | 按命令内容动态判断 |
| 副作用 | 是 |
| 需要审批 | HIGH/CRITICAL 级别需要 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| command | str | 是 | 要执行的命令 |
| cwd | str | 否 | 工作目录，默认当前目录 |
| timeout | int | 否 | 超时秒数，默认 30 |

**返回：**

```json
{
  "ok": true,
  "stdout": "total 48\ndrwxr-xr-x 5 user user 4096 ...",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 120,
  "risk_level": "safe"
}
```

**使用场景：**

- "看看当前目录有什么文件" → `ls -la`
- "查看内存使用" → `free -h`
- "搜索代码中的 TODO" → `grep -r "TODO" src/`

---

### edit_file

编辑本地文件（替换指定内容）。

| 属性 | 值 |
|------|-----|
| 安全等级 | LOW |
| 副作用 | 是 |
| 需要审批 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_path | str | 是 | 文件路径 |
| old_text | str | 是 | 要替换的原文 |
| new_text | str | 是 | 替换后的内容 |

**使用场景：**

- "把配置文件里的端口改成 8080"
- "修改 nginx 配置的 worker_connections"

---

## 2. SSH 远程工具

### ssh_exec

在远程服务器上执行命令。

| 属性 | 值 |
|------|-----|
| 安全等级 | 按命令内容动态判断 |
| 副作用 | 是 |
| 需要审批 | HIGH/CRITICAL 级别需要 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| host | str | 是 | 目标主机名（从 inventory 中查找） |
| command | str | 是 | 要执行的命令 |
| timeout | int | 否 | 超时秒数，默认 30 |

**返回：**

```json
{
  "ok": true,
  "host": "web-01",
  "stdout": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1        40G   12G   28G  30% /",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 450
}
```

**使用场景：**

- "看看 web-01 的磁盘使用率" → `ssh_exec(host="web-01", command="df -h")`
- "查一下 db-master 的 MySQL 状态" → `ssh_exec(host="db-master", command="mysqladmin status")`

---

### ssh_upload

上传文件到远程服务器。

| 属性 | 值 |
|------|-----|
| 安全等级 | LOW |
| 副作用 | 是 |
| 需要审批 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| host | str | 是 | 目标主机 |
| local_path | str | 是 | 本地文件路径 |
| remote_path | str | 是 | 远程目标路径 |

---

### ssh_download

从远程服务器下载文件。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| host | str | 是 | 目标主机 |
| remote_path | str | 是 | 远程文件路径 |
| local_path | str | 是 | 本地保存路径 |

---

## 3. 集群批量工具

### cluster_exec

在多台服务器上执行同一命令。

| 属性 | 值 |
|------|-----|
| 安全等级 | 按命令内容动态判断（最低 HIGH） |
| 副作用 | 是 |
| 需要审批 | 始终需要 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| command | str | 是 | 要执行的命令 |
| targets | str | 否 | 目标筛选，如 "web", "db", "web-01,web-02"，默认 "all" |
| strategy | str | 否 | 执行策略：serial(逐台)/rolling(滚动)，默认 "serial" |
| interval | int | 否 | 每台间隔秒数，默认 5 |

**返回：**

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "failed": 1,
  "results": [
    {"host": "web-01", "ok": true, "stdout": "...", "exit_code": 0},
    {"host": "web-02", "ok": true, "stdout": "...", "exit_code": 0},
    {"host": "web-03", "ok": false, "stderr": "permission denied", "exit_code": 1}
  ]
}
```

**使用场景：**

- "重启所有 Web 服务器的 nginx"
- "检查所有机器的磁盘使用率"
- "在所有服务器上更新 /etc/hosts"

---

### cluster_exec_rolling

滚动执行（用于部署场景）。

| 属性 | 值 |
|------|-----|
| 安全等级 | HIGH |
| 副作用 | 是 |
| 需要审批 | 始终需要 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| command | str | 是 | 要执行的命令 |
| targets | str | 否 | 目标筛选 |
| batch_size | int | 否 | 每批数量，默认 1 |
| health_check | str | 否 | 每批执行后的健康检查命令 |
| rollback_on_failure | bool | 失败时是否自动回滚已完成的，默认 true |

---

## 4. 监控诊断工具

### system_status

查看系统状态。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| host | str | 否 | 目标主机，默认 "local" |

**返回：**

```json
{
  "ok": true,
  "host": "web-01",
  "cpu": {"usage_percent": 25.3, "cores": 4},
  "memory": {"total_gb": 16, "used_gb": 8.2, "percent": 51.2},
  "disk": [
    {"mount": "/", "total_gb": 40, "used_gb": 12, "percent": 30},
    {"mount": "/data", "total_gb": 100, "used_gb": 75, "percent": 75}
  ],
  "load_average": [1.2, 0.8, 0.5],
  "uptime_days": 45
}
```

**使用场景：**

- "看看 web-01 的状态"
- "哪台服务器 CPU 最高？"

---

### check_logs

搜索系统日志。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | str | 是 | 搜索关键词 |
| hosts | str | 否 | 目标主机，支持 "all", "web", 默认 "local" |
| since | str | 否 | 时间范围，如 "1h", "30m", "2026-05-13"，默认 "1h" |
| level | str | 日志级别过滤：error/warn/info，默认不过滤 |
| source | str | 日志来源：syslog/nginx/app，默认自动 |
| limit | int | 否 | 最大返回条数，默认 50 |

**使用场景：**

- "最近有什么错误日志？"
- "web 服务器上有没有 OOM 记录？"
- "今天 nginx 有哪些 5xx 错误？"

---

### check_port

检查端口是否在监听。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| port | int | 是 | 端口号 |
| hosts | str | 否 | 目标主机，默认 "all" |

**使用场景：**

- "80 端口在哪些机器上开着？"
- "web-03 的 3306 端口通不通？"

---

### check_service

检查服务状态。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| service | str | 是 | 服务名，如 "nginx", "mysql", "redis" |
| hosts | str | 否 | 目标主机，默认 "all" |

**使用场景：**

- "nginx 在所有机器上都正常吗？"
- "数据库主从复制状态怎么样？"

---

## 5. Docker 工具

### docker_ps

查看 Docker 容器。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| host | str | 否 | 目标主机，默认 "local" |
| all | bool | 否 | 是否显示已停止的容器，默认 false |

---

### docker_logs

查看容器日志。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| container | str | 是 | 容器名或 ID |
| host | str | 否 | 目标主机，默认 "local" |
| tail | int | 否 | 最后多少行，默认 100 |
| since | str | 否 | 时间范围，默认 "1h" |

---

### docker_restart

重启容器。

| 属性 | 值 |
|------|-----|
| 安全等级 | LOW |
| 副作用 | 是 |
| 需要审批 | 否 |

---

## 6. 部署工具

### deploy

执行部署流程。

| 属性 | 值 |
|------|-----|
| 安全等级 | HIGH |
| 副作用 | 是 |
| 需要审批 | 始终需要 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| service | str | 是 | 服务名 |
| version | str | 否 | 版本号，默认 "latest" |
| targets | str | 否 | 部署目标，默认 "all" |
| strategy | str | 否 | 部署策略：rolling/blue-green，默认 "rolling" |
| pre_check | bool | 否 | 部署前检查，默认 true |
| post_check | bool | 否 | 部署后验证，默认 true |

**内置部署流程：**

```
1. pre_check: 检查磁盘空间、端口占用、依赖服务
2. backup: 备份当前版本
3. pull: 拉取新版本代码/镜像
4. build: 构建（如果需要）
5. stop: 停止当前服务
6. start: 启动新版本
7. health_check: 检查服务是否正常
8. 如果 health_check 失败 → 自动回滚
9. 清理旧版本备份（保留最近 3 个）
```

---

### rollback

回滚上一次部署。

| 属性 | 值 |
|------|-----|
| 安全等级 | HIGH |
| 副作用 | 是 |
| 需要审批 | 始终需要 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| service | str | 是 | 服务名 |
| target | str | 否 | 回滚到哪个版本，默认上一个版本 |

---

## 7. 知识库工具

### ingest_document

导入运维文档到知识库。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_path | str | 是 | 文档路径 |

---

### search_knowledge

从运维知识库中检索。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | str | 是 | 查询内容 |
| limit | int | 否 | 返回条数，默认 4 |

**使用场景：**

- "nginx 502 错误怎么排查？"（自动检索运维手册）
- "MySQL 主从同步断了怎么办？"

---

## 8. 经验沉淀工具

### save_incident_as_skill

将当前排查过程沉淀为 Skill。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | str | 是 | Skill 名称 |
| description | str | 否 | 简要描述（不填则 LLM 自动生成） |
| include_steps | bool | 否 | 是否包含排查步骤，默认 true |

**使用场景：**

- "把刚才的排查过程保存下来"
- "/learn"

---

### list_incidents

查看历史踩坑记录。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | str | 否 | 关键词搜索 |
| severity | str | 否 | 严重级别过滤 |
| limit | int | 否 | 返回条数，默认 20 |

**使用场景：**

- "之前遇到过类似的 502 问题吗？"
- "/incidents nginx"

---

### search_skills

搜索已沉淀的 Skill。

| 属性 | 值 |
|------|-----|
| 安全等级 | SAFE |
| 副作用 | 否 |

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | str | 是 | 搜索内容 |
| tags | str | 否 | 按标签过滤 |

**使用场景：**

- "有没有处理磁盘满的经验？"
- "MySQL 主从同步的排查手册有吗？"

---

## 9. 工具注册示例

```python
from wuwei import ToolRegistry, Agent, LLMGateway
from ai_terminal.safety import SafetyPolicy, SafetyHook
from ai_terminal.tools import (
    register_shell_tools,
    register_ssh_tools,
    register_cluster_tools,
    register_monitor_tools,
    register_docker_tools,
    register_deploy_tools,
)

# 创建工具注册表
registry = ToolRegistry()

# 注册各类工具
register_shell_tools(registry)
register_ssh_tools(registry, ssh_pool=ssh_pool)
register_cluster_tools(registry, cluster_manager=cluster_manager)
register_monitor_tools(registry, cluster_manager=cluster_manager)
register_docker_tools(registry, cluster_manager=cluster_manager)
register_deploy_tools(registry, deployer=deployer)

# 注册 RAG 工具（从 wuwei 内置）
registry = ToolRegistry.from_builtin(["rag"], knowledge_store=knowledge_store)

# 创建安全策略
safety = SafetyPolicy.from_config("~/.ai-terminal/safety.yaml")

# 创建 Agent
agent = Agent(
    llm=LLMGateway.from_env(),
    tools=registry,
    hooks=[
        SafetyHook(safety),                 # 安全审批
        AuditHook(audit_logger),            # 审计日志
        IncidentLearningHook(llm, skill_generator, memory_store),  # 踩坑自动沉淀
        RagRetrievalHook(knowledge_store),  # 运维知识检索
        MemoryRetrievalHook(memory_store),  # 长期记忆
        MemoryExtractionHook(llm, memory_store),
        ConsoleHook(),                      # 控制台输出
    ],
)
```
