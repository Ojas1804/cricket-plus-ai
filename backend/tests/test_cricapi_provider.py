import pytest

from app.cricket.providers.base import ProviderError
from app.cricket.providers.cricapi import CricApiProvider


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def get(self, url, params=None):
        self.requests.append({"url": url, "params": params})
        return FakeResponse(self.payload)


def provider(payload, api_key="test-key"):
    return CricApiProvider(api_key, client=FakeClient({"status": "success", "data": payload}))


def test_list_live_matches_includes_only_unfinished_matches():
    p = provider([
        {"id": "live", "name": "India vs Australia", "matchType": "t20", "matchStarted": True,
         "matchEnded": False, "teams": ["India", "Australia"]},
        {"id": "done", "name": "England vs Pakistan", "matchType": "odi", "matchStarted": True,
         "matchEnded": True, "teams": ["England", "Pakistan"]},
        {"id": "early", "name": "South Africa vs Bangladesh", "matchStarted": False,
         "matchEnded": False, "teams": ["South Africa", "Bangladesh"]},
    ])

    matches = p.list_live_matches()

    assert [m.match_id for m in matches] == ["live"]
    assert matches[0].format == "T20"
    assert matches[0].status == "LIVE"


def test_scorecard_maps_inningsBatting_and_bowling():
    p = provider({
        "id": "m1",
        "name": "India vs Australia, 2nd T20I",
        "matchType": "t20",
        "status": "India need 20 off 12",
        "venue": "Wankhede Stadium",
        "teams": ["India", "Australia"],
        "matchStarted": True,
        "matchEnded": False,
        "score": [
            {"r": 180, "w": 5, "o": 20, "inning": "India Inning 1"},
            {"r": 160, "w": 4, "o": 18.4, "inning": "Australia,India Inning 1"},
        ],
        "scorecard": [
            {
                "inning": "India Inning 1",
                "batting": [{"batsman": {"name": "Rohit Sharma"}, "r": 80, "b": 50, "4s": 8, "6s": 2,
                             "sr": 160, "dismissal-text": "not out"}],
                "bowling": [{"bowler": {"name": "Pat Cummins"}, "o": 4, "m": 0, "r": 30, "w": 2, "eco": 7.5}],
            },
            {
                "inning": "Australia,India Inning 1",
                "batting": [
                    {"batsman": {"name": "Virat Kohli"}, "r": 70, "b": 45, "4s": 6, "6s": 1,
                     "sr": 155.56, "dismissal": "catch", "dismissal-text": "c XYZ b ABC"},
                    {"batsman": {"name": "Shubman Gill"}, "r": 90, "b": 55, "4s": 10, "6s": 2,
                     "sr": 163.64, "dismissal-text": "batting"},
                ],
                "bowling": [{"bowler": {"name": "Jasprit Bumrah"}, "o": 18.4, "m": 1, "r": 55, "w": 3, "eco": 2.97}],
            },
        ],
    })

    match = p.get_scorecard("m1")

    assert match.match_id == "m1"
    assert match.status == "LIVE"
    assert match.current_innings == 2
    assert match.innings[0].team == "India"
    assert match.innings[0].completed is True
    assert match.innings[1].team == "Australia"
    assert match.innings[1].overs == "18.4"
    assert match.innings[1].legal_balls == 112
    assert match.innings[1].completed is False
    assert match.innings[1].batting[1].player == "Shubman Gill"
    assert match.innings[1].batting[1].on_strike is True
    assert match.innings[1].bowling[0].overs == "18.4"
    assert match.target == 181
    assert match.balls_remaining == 8
    assert match.runs_required == 21
    assert match.required_run_rate == 15.75
    assert match.current_run_rate == 8.57


def test_provider_error_does_not_leak_api_key():
    api_key = "secret-api-key"
    client = FakeClient({"status": "failure", "reason": f"invalid {api_key}"})
    p = CricApiProvider(api_key, client=client)

    with pytest.raises(ProviderError) as exc:
        p.list_live_matches()

    assert api_key not in str(exc.value)
    assert "[redacted]" in str(exc.value)
