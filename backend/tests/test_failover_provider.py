from datetime import datetime, timezone

import pytest

from app.cricket.providers.base import ProviderError
from app.cricket.providers.failover import FailoverProvider
from app.live.models import LiveMatch, MatchSummary


class Stub:
    is_mock = False

    def __init__(self, name, ids=(), list_error=None, card_error=None, accepts=None):
        self.name, self.ids, self.list_error, self.card_error = name, list(ids), list_error, card_error
        self.card_calls = []
        if accepts:
            self.accepts_id = accepts

    def list_live_matches(self):
        if self.list_error:
            raise self.list_error
        return [MatchSummary(match_id=i, title=i, format="T20", status="LIVE") for i in self.ids]

    def get_scorecard(self, match_id):
        self.card_calls.append(match_id)
        if self.card_error:
            raise self.card_error
        return LiveMatch(match_id=match_id, title=self.name, format="T20", status="LIVE", status_text="", teams=[],
                         updated_at=datetime.now(timezone.utc))


def test_uses_first_provider_with_live_matches():
    a, b = Stub("a", ["1-1"]), Stub("b", ["22"])

    assert [m.match_id for m in FailoverProvider([a, b]).list_live_matches()] == ["1-1"]


def test_falls_through_on_error_and_on_empty():
    a, b, c = Stub("a", list_error=ProviderError("down")), Stub("b", []), Stub("c", ["33"])

    assert [m.match_id for m in FailoverProvider([a, b, c]).list_live_matches()] == ["33"]


def test_empty_result_is_not_an_error_when_a_provider_succeeded():
    assert FailoverProvider([Stub("a", list_error=ProviderError("down")), Stub("b", [])]).list_live_matches() == []


def test_raises_when_every_provider_fails():
    p = FailoverProvider([Stub("a", list_error=ProviderError("x")), Stub("b", list_error=RuntimeError("y"))])

    with pytest.raises(ProviderError, match="All live score providers failed"):
        p.list_live_matches()


def test_scorecard_is_routed_to_the_owning_provider():
    a, b = Stub("a", list_error=ProviderError("down")), Stub("b", ["22"])
    p = FailoverProvider([a, b])
    p.list_live_matches()

    assert p.get_scorecard("22").title == "b"
    assert a.card_calls == []


def test_unknown_ids_are_routed_by_id_format():
    a = Stub("a", accepts=lambda i: "-" in i)
    b = Stub("b", accepts=lambda i: i.isdigit())

    assert FailoverProvider([a, b]).get_scorecard("22").title == "b"
    assert a.card_calls == []


def test_scorecard_error_does_not_hop_providers_for_owned_ids():
    a, b = Stub("a", ["1-1"], card_error=ProviderError("boom")), Stub("b", ["22"])
    p = FailoverProvider([a, b])
    p.list_live_matches()

    with pytest.raises(ProviderError):
        p.get_scorecard("1-1")
    assert b.card_calls == []


def test_is_mock_only_when_all_providers_are_mock():
    mock, real = Stub("m"), Stub("r")
    mock.is_mock = True

    assert FailoverProvider([mock, real]).is_mock is False
    assert FailoverProvider([mock]).is_mock is True
