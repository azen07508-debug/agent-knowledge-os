from agents import CoderAgent, PlannerAgent, ResearcherAgent, ReviewerAgent


def test_agents_return_dict():
    materials = [
        {"url": "https://a.com/1", "title": "记忆分层", "content": "冷热三层，共 3 条规则。", "source": "web"}
    ]
    for agent in [PlannerAgent(), ResearcherAgent(), CoderAgent(), ReviewerAgent()]:
        context = {"materials": materials} if isinstance(agent, ResearcherAgent) else {}
        result = agent.run("测试任务", context)

        assert isinstance(result, dict)
        assert result["summary"]
        assert result["details"]
        assert isinstance(result["knowledge_points"], list)
        assert isinstance(result["next_actions"], list)
