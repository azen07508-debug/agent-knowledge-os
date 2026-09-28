---
type: skill
status: draft
created: 2026-06-30 20:34:30
updated: 2026-06-30 20:34:30
tags:
  - skill
  - codex
source: agent-knowledge-os
related: []
---

# Codex驱动开发

## 摘要

模拟实现建议：先保持模块边界清晰，再用测试固定输出结构。

## 详情

## 需要创建或修改的文件
- agents/：实现四个 Agent
- runtime/：实现预算、记忆和导出器
- workflows/：实现常见知识库工作流
- tests/：固定核心行为
## 核心代码说明
使用统一 AgentResult 结构返回结果，ObsidianExporter 负责写入带 YAML frontmatter 的 Markdown。
## 运行命令
- python -m runtime.main
## 测试命令
- pytest

## 知识点

- 结构化输出

- Markdown 导出

- 本地 mock

## 错误或风险

- 暂无。

## 下一步

- 运行 demo

- 运行 pytest

- 根据审查结果修复
