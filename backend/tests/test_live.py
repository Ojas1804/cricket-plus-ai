from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.ai.models import Intent, MentionedEntities
from app.ai.orchestrator import handle_prompt, refresh_widget
from app.api.v1.matches import live_service
from app.cricket.providers.base import ProviderError
from app.cricket.providers.mock_live import DEFS, MockLiveProvider, play
from app.live.cache import InMemoryCache, RedisCache
from app.live.polling import next_delay
from app.live.service import GENERIC_ERROR, LiveService
from app.main import app
from app.widgets.schemas import PromptRequest
from tests.test_ai_pipeline import FakeProvider

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
ODI, T20, TEST = DEFS


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def env():
    clock = Clock()
    provider = MockLiveProvider(seconds_per_ball=10, clock=clock)
    now = {"v": NOW}
    service = LiveService(provider, InMemoryCache(), refresh_seconds=60, clock=lambda: now["v"])

    class Env:
        pass

    e = Env()
    e.clock, e.provider, e.service, e.now = clock, provider, service, now

    def tick(seconds):
        clock.advance(seconds)
        now["v"] = now["v"] + timedelta(seconds=seconds)

    e.tick = tick
    return e


def test_simulator_is_internally_consistent():
    for d in DEFS:
        m = play(d, 40, NOW)
        for inn in m.innings:
            assert sum(b.runs for b in inn.batting) <= inn.runs
            assert sum(b.wickets for b in inn.bowling) == inn.wickets
            assert sum(int(b.overs.split(".")[0]) * 6 + int(b.overs.split(".")[1]) for b in inn.bowling) == inn.legal_balls
            assert len(inn.fall_of_wickets) == inn.wickets
            assert [b for b in inn.batting if b.on_strike].__len__() <= 1


def test_simulator_is_deterministic_and_monotonic():
    a, b = play(ODI, 20, NOW), play(ODI, 20, NOW)
    assert a.model_dump() == b.model_dump()
    prev = play(ODI, 0, NOW).innings[0]
    for extra in range(1, 25):
        cur = play(ODI, extra, NOW).innings[0]
        assert cur.runs >= prev.runs and cur.legal_balls - prev.legal_balls <= 1 and cur.wickets >= prev.wickets
        prev = cur


def test_chase_fields_and_result_text():
    m = play(T20, 0, NOW)
    first = m.innings[0].runs
    assert m.status == "LIVE" and m.target == first + 1 and m.required_run_rate is not None
    assert m.runs_required == m.target - m.innings[1].runs and f"need {m.runs_required} runs" in m.status_text
    done = play(T20, 500, NOW)
    assert done.status == "COMPLETED" and ("won by" in done.status_text or "tied" in done.status_text)
    assert done.partnership is None and done.required_run_rate is None


def test_first_fetch_is_on_demand_and_fresh(env):
    res = env.service.list_matches()
    assert {e.match.match_id for e in res.matches} == {ODI.match_id, T20.match_id, TEST.match_id}
    assert all(not e.freshness.stale and e.freshness.is_mock for e in res.matches) and not res.freshness.stale


def test_provider_failure_retains_last_known_and_marks_stale(env):
    env.service.list_matches()
    before = env.service.get_match(ODI.match_id).match
    env.provider.fail = True
    env.tick(60)
    assert env.service.refresh_all() is False
    after = env.service.get_match(ODI.match_id)
    assert after.match.innings[0].runs == before.innings[0].runs
    assert after.freshness.stale and after.freshness.error and after.freshness.last_success_at == NOW
    listing = env.service.list_matches()
    assert listing.freshness.stale and len(listing.matches) == 3

    env.provider.fail = False
    env.tick(60)
    assert env.service.refresh_all() is True
    assert not env.service.get_match(ODI.match_id).freshness.stale


def test_staleness_by_age_without_errors(env):
    env.service.poller_active = True
    env.service.list_matches()
    env.tick(60 * 2 + 4)
    assert not env.service.get_match(ODI.match_id).freshness.stale
    env.tick(2)
    f = env.service.get_match(ODI.match_id).freshness
    assert f.stale and f.error is None


def test_provider_errors_are_not_leaked(env):
    class Broken(MockLiveProvider):
        def list_live_matches(self):
            raise RuntimeError("api_key=SECRET123 exploded")

    service = LiveService(Broken(clock=env.clock), InMemoryCache(), 60, clock=lambda: NOW)
    res = service.list_matches()
    assert res.freshness.error == GENERIC_ERROR and "SECRET" not in str(res.model_dump())


def test_completed_matches_stop_being_tracked_but_remain_readable(env):
    env.service.list_matches()
    env.service.poller_active = True
    env.tick(10 * 400)
    env.service.refresh_all()
    ids = {e.match.match_id for e in env.service.list_matches().matches}
    assert T20.match_id not in ids
    assert env.service.get_match(T20.match_id).match.status == "COMPLETED"


def test_unknown_match_is_404(env):
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        env.service.get_match("nope")


def test_backoff_schedule():
    assert next_delay(60, 0) == 60
    assert [next_delay(60, n) for n in (1, 2, 3, 4)] == [120, 240, 480, 600]
    assert next_delay(60, 50) == 600


def test_cache_expiry_and_redis_degradation(monkeypatch):
    cache = InMemoryCache()
    cache.set("k", {"a": 1}, ttl_seconds=0)
    assert cache.get("k") is None

    class Boom:
        def get(self, *_):
            raise ConnectionError("down")

        def setex(self, *_):
            raise ConnectionError("down")

    r = RedisCache(Boom())
    assert r.get("k") is None
    r.set("k", {"a": 1}, 10)


@pytest.fixture
def client(env):
    app.dependency_overrides[live_service] = lambda: env.service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_live_endpoints(client, env):
    live = client.get("/api/v1/matches/live").json()
    assert len(live["matches"]) == 3 and live["freshness"]["stale"] is False
    one = client.get(f"/api/v1/matches/{ODI.match_id}").json()
    assert one["match"]["teams"] == ["India", "Australia"] and one["freshness"]["is_mock"] is True
    sc = client.get(f"/api/v1/matches/{ODI.match_id}/scorecard").json()
    assert sc["innings"][0]["batting"] and sc["innings"][0]["bowling"]
    assert client.get("/api/v1/matches/nope").status_code == 404


def test_widget_endpoint_is_stateless_and_marks_stale(client, env):
    w = client.get(f"/api/v1/matches/{ODI.match_id}/widget", params={"widgetId": "widget-keep"}).json()
    assert w["id"] == "widget-keep" and w["type"] == "scorecard" and w["metadata"]["isMock"] is True
    assert w["query"]["live"]["matchId"] == ODI.match_id and w["metadata"]["source"] == "live:mock"
    assert w["metadata"]["provenance"]["warnings"] == []

    env.provider.fail = True
    env.tick(60)
    env.service.refresh_all()
    w = client.get(f"/api/v1/matches/{ODI.match_id}/widget").json()
    assert w["metadata"]["provenance"]["stale"] is True and "stale" in w["metadata"]["provenance"]["warnings"][0]
    assert w["data"]["extra"]["stale"] is True and w["data"]["extra"]["innings"]


def test_live_prompt_creates_independent_scorecards_and_refreshes(env, monkeypatch, session):
    monkeypatch.setattr("app.ai.orchestrator.get_live_service", lambda: env.service)
    intent = Intent(kind="live", summary="s", clarification_question="",
                    entities=MentionedEntities(players=[], teams=[], competitions=[], venues=[]))
    res = handle_prompt(PromptRequest(prompt="all live matches"), session, FakeProvider(intent))
    assert [w.type.value for w in res.widgets] == ["scorecard"] * 3 and len({w.id for w in res.widgets}) == 3
    w = res.widgets[0]
    env.tick(120)
    env.service.refresh_all()
    monkeypatch.setattr("app.ai.orchestrator.get_live_service", lambda: env.service)
    refreshed = refresh_widget(session, w.id)
    assert refreshed.id == w.id and refreshed.data.extra["innings"][0]["legal_balls"] >= w.data.extra["innings"][0]["legal_balls"]


def test_no_live_matches_message(env, monkeypatch, session):
    from app.live.widgets import live_widgets

    env.tick(10 * 5000)
    env.service.poller_active = True
    env.service.refresh_all()
    w = live_widgets(env.service)[0]
    assert w.type.value == "text" and "no live matches" in w.data.extra["text"].lower()
    env.provider.fail = True
    env.tick(60)
    env.service.refresh_all()
    w = live_widgets(env.service)[0]
    assert "unavailable" in w.data.extra["text"] and w.metadata.provenance["warnings"]


def test_provider_error_type():
    p = MockLiveProvider()
    p.fail = True
    with pytest.raises(ProviderError):
        p.get_scorecard("x")


@pytest.mark.parametrize("prompt", ["Show all live international matches", "what's the live score?", "current matches in progress", "ongoing cricket matches"])
def test_live_requests_skip_the_llm(env, monkeypatch, session, prompt):
    monkeypatch.setattr("app.ai.orchestrator.get_live_service", lambda: env.service)

    class NoLLM:
        def parse(self, *a):
            raise AssertionError("LLM must not be called for live requests")

    res = handle_prompt(PromptRequest(prompt=prompt), session, NoLLM())
    assert res.status == "COMPLETED" and len(res.widgets) == 3


def test_non_live_prompt_still_uses_pipeline(env):
    from app.ai.orchestrator import LIVE_REQUEST

    assert not LIVE_REQUEST.search("Top 10 run scorers in IPL history")
    assert not LIVE_REQUEST.search("Show the evolution of batting strike rates in T20 cricket")
