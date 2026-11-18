import pytest

from app.cricket.providers.base import ProviderError
from app.cricket.providers.cricdata import CricdataProvider


def match(state="LIVE", fmt="T20", status_text="J & K need 62 runs in 23 balls.", cancelled=False):
    return {
        "objectId": 900, "state": state, "format": fmt, "title": "Elite, Group B", "statusText": status_text,
        "isCancelled": cancelled, "series": {"objectId": 100}, "ground": {"name": "Holkar Cricket Stadium"},
        "teams": [{"team": {"name": "Saurashtra"}}, {"team": {"name": "J & K"}}],
    }


def player(pid, name):
    return {"id": pid, "name": name}


def ball(over_no, ball_no, striker, non_striker, total=0, bat=0, wicket=False, wides=0):
    return {"overNumber": over_no, "ballNumber": ball_no, "batsmanPlayerId": striker, "nonStrikerPlayerId": non_striker,
            "totalRuns": total, "batsmanRuns": bat, "isWicket": wicket, "wides": wides, "noballs": 0, "byes": 0, "legbyes": 0}


def first_innings():
    return {
        "inningNumber": 1, "isCurrent": False, "isBatted": True, "team": {"name": "Saurashtra"}, "runs": 214,
        "wickets": 6, "balls": 120, "totalBalls": 120, "target": 0, "inningOvers": [], "inningFallOfWickets": [],
        "inningBatsmen": [{"player": player(1, "HM Desai"), "battedType": "yes", "runs": 90, "balls": 50, "fours": 9,
                           "sixes": 4, "strikerate": 180, "isOut": False}],
        "inningBowlers": [],
    }


def chase_innings(last_ball):
    return {
        "inningNumber": 2, "isCurrent": True, "isBatted": True, "team": {"name": "J & K"}, "runs": 153, "wickets": 6,
        "balls": 97, "totalBalls": 120, "target": 215,
        "inningBatsmen": [
            {"player": player(10, "Kawalpreet Singh"), "battedType": "yes", "runs": 46, "balls": 33, "fours": 5,
             "sixes": 2, "strikerate": 139.4, "isOut": True,
             "dismissalText": {"short": "caught", "long": "c Fuletra b Sakariya"}},
            {"player": player(11, "Abdul Samad"), "battedType": "yes", "runs": 64, "balls": 31, "fours": 4, "sixes": 5,
             "strikerate": 206.5, "isOut": False},
            {"player": player(12, "Yudhvir Singh"), "battedType": "yes", "runs": 3, "balls": 2, "isOut": False},
            {"player": player(13, "SR Kumar"), "battedType": "DNB", "isOut": False},
        ],
        "inningBowlers": [
            {"player": player(20, "JD Unadkat"), "bowledType": "yes", "balls": 18, "maidens": 0, "conceded": 16,
             "wickets": 2, "economy": 5.33},
            {"player": player(21, "Rested"), "bowledType": "no"},
        ],
        "inningFallOfWickets": [
            {"dismissalBatsman": {"name": "Kawalpreet Singh"}, "fowRuns": 140, "fowWicketNum": 6, "fowOvers": 15.0},
        ],
        "inningOvers": [
            {"overNumber": 15, "overRuns": 9, "balls": [ball(15, i + 1, 11, 10, total=t) for i, t in enumerate([1, 4, 0, 1, 2, 1])]},
            {"overNumber": 16, "overRuns": 13, "requiredRuns": 62, "requiredRunRate": 16.17, "remainingBalls": 23,
             "balls": [ball(16, 1, 11, 12, total=1, bat=1), last_ball]},
        ],
    }


def scorecard(last_ball=None, **kw):
    last_ball = last_ball or ball(16, 2, 12, 11, total=1, bat=1)
    return {"match": match(**kw), "content": {"innings": [first_innings(), chase_innings(last_ball)]}}


class FakeClient:
    def __init__(self, live=None, card=None, error=None):
        self.live, self.card, self.error, self.calls = live, card, error, []

    def live_matches(self):
        if self.error:
            raise self.error
        return self.live

    def match_scorecard(self, series_slug, match_slug):
        self.calls.append((series_slug, match_slug))
        if self.error:
            raise self.error
        return self.card


def test_list_live_matches_returns_only_live_with_composite_ids():
    client = FakeClient(live=[match(), {**match(state="PRE"), "objectId": 901}, {**match(state="POST"), "objectId": 902}])

    matches = CricdataProvider(client=client).list_live_matches()

    assert [(m.match_id, m.title, m.format, m.status) for m in matches] == [
        ("100-900", "Saurashtra vs J & K, Elite, Group B", "T20", "LIVE")]


def test_scorecard_maps_live_chase():
    client = FakeClient(card=scorecard())

    m = CricdataProvider(client=client).get_scorecard("100-900")

    assert client.calls == [("series-100", "match-900")]
    assert (m.status, m.current_innings, m.venue) == ("LIVE", 2, "Holkar Cricket Stadium")
    first, second = m.innings
    assert first.completed is True and first.batting[0].dismissal == "not out"
    assert (second.team, second.runs, second.overs, second.legal_balls, second.completed) == ("J & K", 153, "16.1", 97, False)
    assert [b.player for b in second.batting] == ["Kawalpreet Singh", "Abdul Samad", "Yudhvir Singh"]
    assert second.batting[0].dismissal == "c Fuletra b Sakariya"
    assert second.did_not_bat == ["SR Kumar"]
    assert [b.player for b in second.bowling] == ["JD Unadkat"] and second.bowling[0].overs == "3.0"
    assert second.fall_of_wickets == ["140-6 (Kawalpreet Singh, 15.0 ov)"]
    assert (m.target, m.runs_required, m.balls_remaining, m.required_run_rate) == (215, 62, 23, 16.17)
    assert m.current_run_rate == 9.46
    assert m.partnership.runs == 13 and m.partnership.balls == 7
    assert [(o.over, o.balls, o.runs) for o in m.recent_overs] == [(15, ["1", "4", "0", "1", "2", "1"], 9), (16, ["1", "1"], 13)]


@pytest.mark.parametrize("last_ball,expected", [
    (ball(16, 2, 12, 11, total=1, bat=1), 11),
    (ball(16, 2, 12, 11, total=0), 12),
    (ball(16, 6, 12, 11, total=0), 11),
    (ball(16, 6, 12, 11, total=1, bat=1), 12),
])
def test_striker_follows_odd_runs_and_over_end(last_ball, expected):
    m = CricdataProvider(client=FakeClient(card=scorecard(last_ball))).get_scorecard("100-900")

    on_strike = [b for b in m.innings[1].batting if b.on_strike]
    assert [b.player for b in on_strike] == [{11: "Abdul Samad", 12: "Yudhvir Singh"}[expected]]


def test_striker_unknown_right_after_wicket():
    m = CricdataProvider(client=FakeClient(card=scorecard(ball(16, 2, 12, 11, wicket=True)))).get_scorecard("100-900")

    assert not any(b.on_strike for b in m.innings[1].batting)
    assert m.recent_overs[-1].balls[-1] == "W"


def test_wide_ball_token():
    m = CricdataProvider(client=FakeClient(card=scorecard(ball(16, 2, 12, 11, total=1, wides=1)))).get_scorecard("100-900")

    assert m.recent_overs[-1].balls[-1] == "Wd"


def test_completed_match_has_no_live_fields():
    card = scorecard(state="POST", status_text="Saurashtra won by 5 runs")
    card["content"]["innings"][1]["isCurrent"] = False

    m = CricdataProvider(client=FakeClient(card=card)).get_scorecard("100-900")

    assert m.status == "COMPLETED"
    assert all(i.completed for i in m.innings)
    assert all(not b.on_strike for i in m.innings for b in i.batting)
    assert m.target is None and m.partnership is None and m.recent_overs == []


def test_upcoming_match_strips_template_placeholders():
    card = {"match": match(state="PRE", status_text="Match starts in {{MATCH_START_HOURS}} {{MATCH_START_MINS}}"),
            "content": {"innings": []}}

    m = CricdataProvider(client=FakeClient(card=card)).get_scorecard("100-900")

    assert m.status == "UPCOMING"
    assert m.status_text == "Match yet to begin"
    assert m.innings == [] and m.current_innings is None


def test_library_errors_become_provider_errors():
    p = CricdataProvider(client=FakeClient(error=RuntimeError("curl: (35) boom")))

    with pytest.raises(ProviderError):
        p.list_live_matches()
    with pytest.raises(ProviderError):
        p.get_scorecard("100-900")


def test_invalid_match_id_is_rejected():
    with pytest.raises(ProviderError, match="Invalid"):
        CricdataProvider(client=FakeClient()).get_scorecard("151334")


def test_accepts_id_distinguishes_cricdata_ids():
    assert CricdataProvider.accepts_id("100-900")
    assert not CricdataProvider.accepts_id("151334")
    assert not CricdataProvider.accepts_id("a3f1-4b2c-9d")
