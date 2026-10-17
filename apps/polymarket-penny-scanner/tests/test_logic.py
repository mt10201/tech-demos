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

from backtest_bands import first_entry, tail_risk, fee_per_dollar

def test_first_entry_window_and_buffer():
    pts = [(0, 0.5), (100, 0.85), (250, 0.92), (290, 0.93)]
    assert first_entry(pts, 300, (0.80, 0.90), False, None) == (100, 0.85)
    assert first_entry(pts, 300, (0.90, 0.95), False, 60) == (250, 0.92)
    assert first_entry(pts, 300, (0.90, 0.95), False, 30) is None  # 290 is inside the 15 s buffer
    assert first_entry([(0, 0.2), (60, 0.07)], 300, (0.05, 0.10), True, None) == (60, 0.07)

def test_tail_risk_and_fee():
    r = tail_risk([{"t": 1, "won": True, "price": 0.9}, {"t": 2, "won": False, "price": 0.9}, {"t": 3, "won": False, "price": 0.9}])
    assert r["worst_losing_streak"] == 2 and r["max_drawdown_$"] == 200
    assert fee_per_dollar(0.9) == pytest.approx(0.007)
