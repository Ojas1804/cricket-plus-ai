import pytest

from app.cricket.providers.base import ProviderError
from app.cricket.providers.cricbuzz import CricbuzzProvider

LIVE_PAGE = """
<a href="/live-cricket-scores/100/eng-vs-aus-3rd-odi">x</a>
<a href="/live-cricket-scores/100/eng-vs-aus-3rd-odi-again">x</a>
<a href="/live-cricket-scores/200/nz-vs-ind-1st-test">x</a>
<a href="/live-cricket-scores/300/del-vs-bih-t20">x</a>
"""


def header(state="In Progress", complete=False, fmt="ODI", status="Australia need 121 runs in 54 balls"):
    return {
        "matchId": 100, "matchDescription": "3rd ODI", "matchFormat": fmt, "complete": complete, "state": state,
        "status": status, "team1": {"id": 4, "name": "Australia"}, "team2": {"id": 9, "name": "England"},
        "venue": {"name": "Bellerive Oval", "city": "Hobart"},
    }


def comm_payload(hdr):
    return {
        "matchHeader": hdr,
        "miniscore": {
            "inningsId": 2, "target": 329, "currentRunRate": 5.07, "requiredRunRate": 13.44,
            "partnerShip": {"balls": 10, "runs": 5},
            "batsmanStriker": {"id": 2, "name": "Mahli Beardman"},
            "batsmanNonStriker": {"id": 3, "name": "Spencer Johnson"},
        },
        "matchCommentary": {
            "a": {"commType": "over-separator", "inningsId": 2,
                  "overSeparator": {"overNumber": 41, "overSummary": "Wd 1 1 0 0 1 0 ", "overRuns": 4}},
            "b": {"commType": "over-separator", "inningsId": 2,
                  "overSeparator": {"overNumber": 40, "overSummary": "0 0 1 4 0 W", "overRuns": 5}},
            "c": {"commType": "over-separator", "inningsId": 1,
                  "overSeparator": {"overNumber": 48, "overSummary": "1 1 1 1 1 1", "overRuns": 6}},
            "d": {"commType": "commentary", "inningsId": 2, "commText": "no run"},
        },
    }


def scorecard_payload():
    return {"scoreCard": [
        {
            "inningsId": 1,
            "batTeamDetails": {"batTeamName": "England", "batsmenData": {
                "bat_1": {"batId": 1, "batName": "Tom Banton", "runs": 44, "balls": 35, "fours": 9, "sixes": 0,
                          "strikeRate": 125.71, "outDesc": "c Mitchell Marsh b Jack Edwards"}}},
            "bowlTeamDetails": {"bowlersData": {
                "bowl_1": {"bowlName": "Xavier Bartlett", "overs": 7, "balls": 42, "maidens": 0, "runs": 66,
                           "wickets": 1, "economy": 9.4}}},
            "scoreDetails": {"ballNbr": 291, "overs": 48.3, "runs": 328, "wickets": 10},
            "wicketsData": {"wkt_1": {"batName": "Tom Banton", "wktOver": 8.4, "wktRuns": 74, "wktNbr": 1}},
        },
        {
            "inningsId": 2,
            "batTeamDetails": {"batTeamName": "Australia", "batsmenData": {
                "bat_1": {"batId": 2, "batName": "Mahli Beardman", "runs": 3, "balls": 7, "outDesc": "batting",
                          "strikeRate": "42.86"},
                "bat_2": {"batId": 3, "batName": "Spencer Johnson", "runs": 5, "balls": 4, "fours": 1,
                          "outDesc": "batting"},
                "bat_3": {"batId": 4, "batName": "Yet To Bat", "runs": 0, "balls": 0, "outDesc": ""}}},
            "bowlTeamDetails": {"bowlersData": {
                "bowl_1": {"bowlName": "Liam Dawson", "overs": 9, "balls": 54, "maidens": 0, "runs": 34,
                           "wickets": 3, "economy": 3.78}}},
            "scoreDetails": {"ballNbr": 246, "overs": 41, "runs": 208, "wickets": 9},
            "wicketsData": {},
        },
    ]}


class FakeResponse:
    def __init__(self, payload=None, text="", status_code=200):
        self.status_code, self._payload, self.text = status_code, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    def __init__(self, routes):
        self.routes, self.requests = routes, []

    def get(self, url, params=None):
        self.requests.append(url)
        for suffix, response in self.routes.items():
            if url.endswith(suffix):
                return response
        return FakeResponse(status_code=404)


def provider(routes):
    return CricbuzzProvider(client=FakeClient(routes), cache_seconds=0)


def live_routes(hdr=None):
    hdr = hdr or header()
    return {"api/mcenter/comm/100": FakeResponse(comm_payload(hdr)),
            "api/mcenter/scorecard/100": FakeResponse(scorecard_payload())}


def test_list_live_matches_keeps_only_in_progress_and_dedupes_ids():
    p = provider({
        "cricket-match/live-scores": FakeResponse(text=LIVE_PAGE),
        "api/mcenter/comm/100": FakeResponse(comm_payload(header())),
        "api/mcenter/comm/200": FakeResponse(comm_payload(header(state="Preview"))),
        "api/mcenter/comm/300": FakeResponse(comm_payload(header(state="Complete", complete=True))),
    })

    matches = p.list_live_matches()

    assert [m.match_id for m in matches] == ["100"]
    assert matches[0].title == "Australia vs England, 3rd ODI"
    assert matches[0].format == "ODI"
    assert matches[0].status == "LIVE"
    assert sum(u.endswith("comm/100") for u in p._client.requests) == 1


def test_list_live_matches_skips_matches_whose_header_fails():
    p = provider({
        "cricket-match/live-scores": FakeResponse(text=LIVE_PAGE),
        "api/mcenter/comm/100": FakeResponse(comm_payload(header())),
    })

    assert [m.match_id for m in p.list_live_matches()] == ["100"]


def test_scorecard_maps_live_chase():
    match = provider(live_routes()).get_scorecard("100")

    assert match.status == "LIVE"
    assert match.title == "Australia vs England, 3rd ODI"
    assert match.venue == "Bellerive Oval, Hobart"
    assert match.teams == ["Australia", "England"]
    assert match.current_innings == 2
    first, second = match.innings
    assert (first.team, first.runs, first.overs, first.completed) == ("England", 328, "48.3", True)
    assert first.batting[0].dismissal == "c Mitchell Marsh b Jack Edwards"
    assert first.bowling[0].overs == "7.0"
    assert first.fall_of_wickets == ["74-1 (Tom Banton, 8.4 ov)"]
    assert (second.team, second.wickets, second.overs, second.legal_balls, second.completed) == ("Australia", 9, "41.0", 246, False)
    assert [b.player for b in second.batting] == ["Mahli Beardman", "Spencer Johnson"]
    assert second.batting[0].on_strike is True
    assert second.batting[1].on_strike is False
    assert second.batting[0].dismissal == "not out"
    assert match.target == 329
    assert match.runs_required == 121
    assert match.balls_remaining == 54
    assert match.required_run_rate == 13.44
    assert match.current_run_rate == 5.07
    assert match.partnership.runs == 5 and match.partnership.batters == ["Mahli Beardman", "Spencer Johnson"]
    assert [(o.over, o.balls, o.runs) for o in match.recent_overs] == [(40, ["0", "0", "1", "4", "0", "W"], 5),
                                                                       (41, ["Wd", "1", "1", "0", "0", "1", "0"], 4)]


def test_scorecard_completed_match_has_no_live_fields():
    hdr = header(state="Complete", complete=True, status="England won by 20 runs")

    match = provider(live_routes(hdr)).get_scorecard("100")

    assert match.status == "COMPLETED"
    assert all(i.completed for i in match.innings)
    assert all(not b.on_strike for i in match.innings for b in i.batting)
    assert match.target is None and match.partnership is None and match.recent_overs == []


def test_upcoming_match_has_no_innings():
    routes = {"api/mcenter/comm/100": FakeResponse({"matchHeader": header(state="Preview"), "miniscore": {}}),
              "api/mcenter/scorecard/100": FakeResponse({"scoreCard": []})}

    match = provider(routes).get_scorecard("100")

    assert match.status == "UPCOMING"
    assert match.innings == [] and match.current_innings is None


def test_http_error_raises_provider_error():
    with pytest.raises(ProviderError, match="HTTP 404"):
        provider({}).get_scorecard("100")


def test_invalid_json_raises_provider_error():
    with pytest.raises(ProviderError, match="invalid JSON"):
        provider({"api/mcenter/comm/100": FakeResponse(None)}).get_scorecard("100")


def test_malformed_innings_data_is_tolerated():
    routes = live_routes()
    routes["api/mcenter/scorecard/100"] = FakeResponse({"scoreCard": [{"batTeamDetails": {"batsmenData": {"x": 1}},
                                                                       "scoreDetails": "bad"}]})
    match = provider(routes).get_scorecard("100")
    assert match.innings[0].runs == 0


def test_responses_are_cached_briefly():
    p = CricbuzzProvider(client=FakeClient(live_routes()), cache_seconds=60)

    p.get_scorecard("100")
    p.get_scorecard("100")

    assert len(p._client.requests) == 2
