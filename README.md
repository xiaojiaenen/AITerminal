# AI Terminal

智能终端管家 — 用自然语言操作终端、管理集群。

基于 [Wuwei](https://github.com/xiaojiaenen/wuwei) Agent 框架构建。

## 功能

- 自然语言操作终端
- 多服务器集群管理
- 安全策略（命令分级 + 确认流程 + 审计日志）
- 运维知识库（RAG）
- 经验自动沉淀为 Skill

## 安装

```bash
pip install -e .
```

## 使用

```bash
ai-terminal
```

## 输入模式

| 前缀 | 模式 | 示例 |
|------|------|------|
| 无 | AI 对话 | "看看磁盘使用率" |
| `!` | 直接执行 | `!docker ps` |
| `>` | 混合模式 | "> 清理日志" |
| `/` | 快捷命令 | `/status` |
