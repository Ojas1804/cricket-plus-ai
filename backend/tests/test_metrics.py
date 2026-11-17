from app.analytics.metrics import cricket_metrics as m


def test_batting_average_and_not_out_career():
    assert m.batting_average(5000, 100) == 50.0
    assert m.batting_average(120, 0) is None


def test_strike_rate():
    assert m.batting_strike_rate(50, 40) == 125.0
    assert m.batting_strike_rate(0, 0) is None


def test_bowling_metrics():
    assert m.bowling_economy(30, 24) == 7.5
    assert m.bowling_average(60, 3) == 20.0
    assert m.bowling_strike_rate(24, 3) == 8.0
    assert m.bowling_average(60, 0) is None


def test_overs_notation():
    assert m.overs_notation(23) == "3.5"


def test_legal_delivery_and_extras():
    assert not m.is_legal_delivery({"wides": 1})
    assert not m.is_legal_delivery({"noballs": 1})
    assert m.is_legal_delivery({"legbyes": 1})
    assert m.is_legal_delivery(None)


def test_runs_charged_to_bowler():
    assert m.runs_charged_to_bowler(5, {"wides": 5}) == 5
    assert m.runs_charged_to_bowler(4, {"byes": 4}) == 0
    assert m.runs_charged_to_bowler(1, {"legbyes": 1}) == 0
    assert m.runs_charged_to_bowler(6, {"noballs": 1}) == 6
    assert m.runs_charged_to_bowler(5, {"penalty": 5}) == 0


def test_wicket_credit_and_dismissals():
    assert m.is_bowler_wicket("bowled") and m.is_bowler_wicket("caught")
    assert not m.is_bowler_wicket("run out")
    assert not m.is_bowler_wicket("retired hurt")
    assert m.is_batting_dismissal("run out")
    assert not m.is_batting_dismissal("retired hurt")


def test_balls_faced():
    assert not m.batter_faced_ball({"wides": 1})
    assert m.batter_faced_ball({"noballs": 1})
