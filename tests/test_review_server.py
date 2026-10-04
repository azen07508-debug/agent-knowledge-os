from runtime.review_server import ReviewHandler


def test_review_handler_declares_local_cors_policy():
    assert "Access-Control-Allow-Origin" in ReviewHandler.cors_headers()
    assert ReviewHandler.cors_headers()["Access-Control-Allow-Origin"] == "*"
