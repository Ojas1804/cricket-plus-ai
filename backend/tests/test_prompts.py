from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _post(prompt, action="ADD", target=None):
    return client.post("/api/v1/prompts", json={"prompt": prompt, "action": action, "targetWidgetId": target})


def test_add_creates_independent_widgets():
    a = _post("Show the top 10 IPL run scorers").json()["widgets"][0]
    b = _post("Compare Virat Kohli and Rohit Sharma").json()["widgets"][0]
    assert a["type"] == "leaderboard" and b["type"] == "comparison" and a["id"] != b["id"]


def test_multiple_widgets_from_one_prompt():
    widgets = _post("Compare Virat Kohli and Rohit Sharma and show their performance trends").json()["widgets"]
    assert [w["type"] for w in widgets] == ["comparison", "chart"]


def test_update_preserves_id():
    w = _post("Show the top 10 IPL run scorers").json()["widgets"][0]
    u = _post("Only players with at least 50 matches", "UPDATE", w["id"]).json()["widgets"][0]
    assert u["id"] == w["id"] and u["query"]["minMatches"] == 50


def test_update_unknown_widget_404():
    assert _post("x", "UPDATE", "nope").status_code == 404


def test_refresh_and_duplicate_registration():
    w = _post("Show the top 10 IPL run scorers").json()["widgets"][0]
    r = client.post(f"/api/v1/widgets/{w['id']}/refresh")
    assert r.status_code == 200 and r.json()["id"] == w["id"]
    copy = {**w, "id": "widget-copy"}
    assert client.post("/api/v1/widgets", json=copy).status_code == 201
    assert client.delete("/api/v1/widgets/widget-copy").status_code == 204
    assert client.get("/api/v1/widgets/widget-copy").status_code == 404
