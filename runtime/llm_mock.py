"""本地 LLM mock。

真实大模型 API 暂不接入，避免需要 API Key 或外部网络。
"""

from __future__ import annotations


def mock_llm_call(prompt: str) -> str:
    """根据提示词返回稳定的中文模拟结果，便于后续替换真实 LLM。"""
    lower_prompt = prompt.lower()
    if "风险" in prompt or "review" in lower_prompt:
        return "模拟审查：重点关注本地服务暴露、敏感信息写入和依赖缺失。"
    if "代码" in prompt or "实现" in prompt:
        return "模拟实现建议：先保持模块边界清晰，再用测试固定输出结构。"
    if "分析" in prompt or "research" in lower_prompt:
        return "模拟研究结论：EverOS 管记忆，Arbiter 管预算，Obsidian 管人类可读沉淀。"
    return "模拟规划：先拆解任务，再执行、审查、写入知识库。"
