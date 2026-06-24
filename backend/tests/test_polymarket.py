"""Resolution detection (settlement bug): a market whose deadline has passed and
whose price is decisive (~0/1) must resolve even if Polymarket hasn't set `closed`
yet (it lags behind the UMA dispute window)."""
from app.data import polymarket

PAST = "2000-01-01T00:00:00Z"
FUTURE = "2099-01-01T00:00:00Z"


def _m(yes, closed=False, end=PAST):
    return {"outcomes": ["Yes", "No"], "outcomePrices": [str(yes), str(1 - yes)],
            "closed": closed, "endDate": end}


def test_deadline_passed_and_decisive_resolves():
    assert polymarket._price_status(_m(0.0005))[1:3] == ("resolved", 0)  # YES lost
    assert polymarket._price_status(_m(0.9995))[1:3] == ("resolved", 1)  # YES won


def test_before_deadline_does_not_resolve_even_if_decisive():
    s = polymarket._price_status(_m(0.0005, end=FUTURE))
    assert s[1] == "open" and s[2] is None


def test_closed_but_ambiguous_is_void():
    assert polymarket._price_status(_m(0.5, closed=True))[1] == "void"


def test_ended_but_ambiguous_stays_open():
    # deadline passed, price not decisive, not closed -> wait for finalization
    assert polymarket._price_status(_m(0.5))[1] == "open"
