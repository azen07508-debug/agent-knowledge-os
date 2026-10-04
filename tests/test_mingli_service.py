"""应用服务层测试。"""

import pytest

from runtime.mingli_service import MingLiService


def birth_data():
    return {"year": 1990, "month": 2, "day": 1, "hour": 12}


def test_service_returns_complete_traceable_response():
    response = MingLiService().analyze(birth_data(), "事业")
    result = response.to_dict()

    assert result["chart"]["provider"] == "sxtwl"
    assert result["chart"]["pillars"]
    assert result["analysis"]["evidence"]["facts"]
    assert "rules" in result["analysis"]["evidence"]
    assert "passed" in result["critique"]


def test_service_rejects_empty_question():
    with pytest.raises(ValueError, match="问题不能为空"):
        MingLiService().analyze(birth_data(), "")
