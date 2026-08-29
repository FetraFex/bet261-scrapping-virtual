"""
Tests for ML baseline models and evaluation metrics.
"""
import pytest
import numpy as np
from typing import List, Tuple

from app.ml.baselines import (
    odds_to_market_probabilities,
    compute_overround,
    MajorityClassBaseline,
    MarketBaseline,
    Prediction,
    log_loss,
    brier_score,
    accuracy,
    class_precision_recall,
    calibration_bins,
    evaluate_baseline,
    odds_movement_features,
    build_match_features,
)


# ---------------------------------------------------------------------------
# Odds conversion tests
# ---------------------------------------------------------------------------

class TestOddsToMarketProbabilities:
    def test_basic_conversion(self):
        p_home, p_draw, p_away = odds_to_market_probabilities(2.0, 3.0, 4.0)
        assert abs(p_home + p_draw + p_away - 1.0) < 1e-10
        assert p_home > p_draw > p_away  # lower odds = higher probability

    def test_equal_odds(self):
        p_home, p_draw, p_away = odds_to_market_probabilities(3.0, 3.0, 3.0)
        assert abs(p_home - 1 / 3) < 1e-10
        assert abs(p_draw - 1 / 3) < 1e-10
        assert abs(p_away - 1 / 3) < 1e-10

    def test_extreme_odds(self):
        p_home, p_draw, p_away = odds_to_market_probabilities(1.01, 100.0, 100.0)
        assert p_home > 0.9  # heavily favored
        assert abs(p_home + p_draw + p_away - 1.0) < 1e-10

    def test_overround_1(self):
        """With no overround (theoretical fair odds), probabilities should be exact."""
        p_home, p_draw, p_away = odds_to_market_probabilities(
            2.0, 3.0, 6.0  # 1/2 + 1/3 + 1/6 = 1.0
        )
        assert abs(p_home - 0.5) < 1e-10
        assert abs(p_draw - (1 / 3)) < 1e-10
        assert abs(p_away - (1 / 6)) < 1e-10


class TestOverround:
    def test_fair_odds(self):
        assert abs(compute_overround(2.0, 3.0, 6.0) - 1.0) < 1e-10

    def test_bookmaker_odds(self):
        overround = compute_overround(1.67, 3.63, 5.37)
        assert overround > 1.0
        assert overround < 1.5  # reasonable margin


# ---------------------------------------------------------------------------
# Majority class baseline tests
# ---------------------------------------------------------------------------

class TestMajorityClassBaseline:
    def test_fit_and_predict(self):
        baseline = MajorityClassBaseline()
        y = ["HOME", "HOME", "HOME", "DRAW", "AWAY"]
        baseline.fit(y)

        probs = baseline.predict_proba(3)
        assert probs.shape == (3, 3)
        assert abs(probs[0][0] - 0.6) < 1e-10  # 3/5 HOME
        assert abs(probs[0][1] - 0.2) < 1e-10  # 1/5 DRAW
        assert abs(probs[0][2] - 0.2) < 1e-10  # 1/5 AWAY

    def test_all_home(self):
        baseline = MajorityClassBaseline()
        baseline.fit(["HOME", "HOME", "HOME"])
        probs = baseline.predict_proba(1)
        assert probs[0][0] == 1.0  # 100% HOME

    def test_unfitted_raises(self):
        baseline = MajorityClassBaseline()
        with pytest.raises(RuntimeError):
            baseline.predict_proba(1)


# ---------------------------------------------------------------------------
# Market baseline tests
# ---------------------------------------------------------------------------

class TestMarketBaseline:
    def test_predict(self):
        baseline = MarketBaseline()
        pred = baseline.predict(2.0, 3.0, 6.0)
        assert abs(pred.probability_sum - 1.0) < 1e-10
        assert pred.p_home == pytest.approx(0.5, abs=1e-10)

    def test_prediction_class(self):
        baseline = MarketBaseline()
        pred = baseline.predict(1.5, 4.0, 6.0)
        assert pred.predicted_class == "HOME"  # lowest odds


# ---------------------------------------------------------------------------
# Evaluation metric tests
# ---------------------------------------------------------------------------

class TestLogLoss:
    def test_perfect_predictions(self):
        y_true = ["HOME", "DRAW", "AWAY"]
        y_pred = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        ll = log_loss(y_true, y_pred)
        assert ll < 0.01  # near zero

    def test_bad_predictions(self):
        y_true = ["HOME", "DRAW", "AWAY"]
        y_pred = [(0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
        ll = log_loss(y_true, y_pred)
        assert ll > 5.0  # very bad

    def test_uniform_predictions(self):
        y_true = ["HOME", "DRAW", "AWAY"]
        y_pred = [(1 / 3, 1 / 3, 1 / 3)] * 3
        ll = log_loss(y_true, y_pred)
        expected = -np.log(1 / 3)
        assert abs(ll - expected) < 1e-10


class TestBrierScore:
    def test_perfect_predictions(self):
        y_true = ["HOME", "DRAW", "AWAY"]
        y_pred = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        bs = brier_score(y_true, y_pred)
        assert bs == pytest.approx(0.0)

    def test_worst_predictions(self):
        y_true = ["HOME", "DRAW", "AWAY"]
        y_pred = [(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        bs = brier_score(y_true, y_pred)
        assert bs == pytest.approx(2.0)  # all wrong, max Brier

    def test_uniform_predictions(self):
        y_true = ["HOME"]
        y_pred = [(1 / 3, 1 / 3, 1 / 3)]
        bs = brier_score(y_true, y_pred)
        expected = (1 / 3) ** 2 + (2 / 3) ** 2 + (1 / 3) ** 2
        assert abs(bs - expected) < 1e-10


class TestAccuracy:
    def test_perfect(self):
        y_true = ["HOME", "DRAW", "AWAY"]
        y_pred = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
        assert accuracy(y_true, y_pred) == pytest.approx(1.0)

    def test_zero_accuracy(self):
        y_true = ["HOME", "HOME"]
        y_pred = [(0.0, 0.0, 1.0), (0.0, 1.0, 0.0)]
        assert accuracy(y_true, y_pred) == pytest.approx(0.0)


class TestClassPrecisionRecall:
    def test_home_precision(self):
        y_true = ["HOME", "HOME", "AWAY"]
        y_pred = [
            (0.8, 0.1, 0.1),
            (0.6, 0.2, 0.2),
            (0.1, 0.1, 0.8),
        ]
        metrics = class_precision_recall(y_true, y_pred, "HOME")
        assert metrics["precision"] == pytest.approx(1.0)
        assert metrics["recall"] == pytest.approx(1.0)

    def test_away_recall(self):
        y_true = ["HOME", "AWAY", "AWAY"]
        y_pred = [
            (0.8, 0.1, 0.1),  # predicted HOME (false negative for AWAY)
            (0.1, 0.1, 0.8),  # predicted AWAY
            (0.1, 0.1, 0.8),  # predicted AWAY
        ]
        metrics = class_precision_recall(y_true, y_pred, "AWAY")
        assert metrics["recall"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Calibration tests
# ---------------------------------------------------------------------------

class TestCalibration:
    def test_perfect_calibration(self):
        y_true = ["HOME", "AWAY"]
        y_pred = [(0.9, 0.05, 0.05), (0.1, 0.1, 0.8)]
        cal = calibration_bins(y_true, y_pred, "HOME", n_bins=5)
        assert len(cal["bin_centers"]) > 0
        assert len(cal["observed_frequencies"]) > 0


# ---------------------------------------------------------------------------
# Evaluation pipeline test
# ---------------------------------------------------------------------------

class TestEvaluateBaseline:
    def test_evaluate(self):
        y_true = ["HOME", "HOME", "DRAW", "AWAY"]
        y_pred = [
            (0.6, 0.2, 0.2),
            (0.5, 0.3, 0.2),
            (0.3, 0.4, 0.3),
            (0.2, 0.2, 0.6),
        ]
        result = evaluate_baseline("test", y_true, y_pred)
        assert result.name == "test"
        assert result.n_samples == 4
        assert result.log_loss > 0
        assert result.brier_score >= 0
        assert 0 <= result.accuracy <= 1
        assert "HOME" in result.class_metrics
        assert "DRAW" in result.class_metrics
        assert "AWAY" in result.class_metrics


# ---------------------------------------------------------------------------
# Odds movement features
# ---------------------------------------------------------------------------

class TestOddsMovementFeatures:
    def test_basic_movement(self):
        snapshots = [
            {"captured_at": "2026-08-24T20:00:00Z", "home_odds": 2.0, "draw_odds": 3.0, "away_odds": 4.0},
            {"captured_at": "2026-08-24T21:00:00Z", "home_odds": 1.9, "draw_odds": 3.2, "away_odds": 4.5},
        ]
        features = odds_movement_features(snapshots)
        assert features["opening_home_odds"] == 2.0
        assert features["latest_home_odds"] == 1.9
        assert features["odds_home_movement"] == pytest.approx(-0.1)
        assert features["n_snapshots"] == 2

    def test_empty_snapshots(self):
        features = odds_movement_features([])
        assert features == {}


# ---------------------------------------------------------------------------
# Feature building
# ---------------------------------------------------------------------------

class TestBuildMatchFeatures:
    def test_minimal_features(self):
        match_row = {"home_odds": 2.0, "draw_odds": 3.0, "away_odds": 6.0}
        features = build_match_features(match_row)
        assert "implied_home_prob" in features
        assert "overround" in features
        assert features["is_home"] == 1.0

    def test_with_ranking(self):
        match_row = {"home_odds": 2.0, "draw_odds": 3.0, "away_odds": 6.0}
        home_rank = {"rank": 1, "points": 32}
        away_rank = {"rank": 5, "points": 24}
        features = build_match_features(match_row, home_rank, away_rank)
        assert features["home_rank"] == 1
        assert features["away_rank"] == 5
        assert features["rank_diff"] == -4
        assert features["points_diff"] == 8

    def test_with_form(self):
        match_row = {}
        home_form = ["Won", "Won", "Draw", "Lost", "Won"]
        away_form = ["Lost", "Lost", "Draw", "Draw", "Lost"]
        features = build_match_features(match_row, home_form=home_form, away_form=away_form)
        assert features["home_form_points"] == 2  # 1+1+0-1+1
        assert features["away_form_wins"] == 0
        assert features["away_form_points"] == -3  # -1-1+0+0-1
