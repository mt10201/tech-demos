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
