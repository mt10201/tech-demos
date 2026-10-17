import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from logic import payoff, penny_sides, history_summary

def test_payoff_penny():
    p = payoff(10, 0.02)
    assert p["shares"] == pytest.approx(500)
    assert p["payout_if_win"] == pytest.approx(500)
    assert p["profit_if_win"] == pytest.approx(490)
    assert p["breakeven_win_rate"] == pytest.approx(0.02)

def test_payoff_bad_price():
    with pytest.raises(ValueError):
        payoff(10, 0)

def test_threshold_filter():
    m = [{"outcomes": ["Up", "Down"], "prices": [0.985, 0.015], "tokens": ["a", "b"]},
         {"outcomes": ["Up", "Down"], "prices": [0.5, 0.5], "tokens": ["c", "d"]},
         {"outcomes": ["Up", "Down"], "prices": [1.0, 0.0], "tokens": ["e", "f"]}]
    rows = penny_sides(m, 0.02)
    assert [(r["side"], r["token"]) for r in rows] == [("Down", "b")]
    assert len(penny_sides(m, 0.015)) == 1 and len(penny_sides(m, 0.01)) == 0

def test_history_summary():
    s = history_summary([{"touched": True, "won": False}, {"touched": True, "won": True}, {"touched": False, "won": True}])
    assert s == {"sides_checked": 3, "touched": 2, "won": 1, "hit_rate": 0.5}

from backtest import wilson, ev_per_dollar, duration_label

def test_wilson_and_ev():
    lo, hi = wilson(0, 100)
    assert lo == 0 and hi == pytest.approx(0.037, abs=1e-3)
    assert ev_per_dollar(True, 0.02) == pytest.approx(49) and ev_per_dollar(False, 0.02) == -1

def test_duration_label():
    assert duration_label("Bitcoin Up or Down - October 16, 11:55PM-12:00AM ET") == "5m"
    assert duration_label("Bitcoin Up or Down - October 16, 2PM ET") == "1h"
    assert duration_label("Bitcoin Up or Down - October 16, 12:00PM-4:00PM ET") == "4h"
