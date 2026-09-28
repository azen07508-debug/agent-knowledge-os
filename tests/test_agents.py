from agents import CoderAgent, PlannerAgent, ResearcherAgent, ReviewerAgent


def test_agents_return_dict():
    for agent in [PlannerAgent(), ResearcherAgent(), CoderAgent(), ReviewerAgent()]:
        result = agent.run("测试任务", {})

        assert isinstance(result, dict)
        assert result["summary"]
        assert result["details"]
        assert isinstance(result["knowledge_points"], list)
        assert isinstance(result["next_actions"], list)
