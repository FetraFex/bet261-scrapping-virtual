"""
Baseline prediction models for virtual football match outcomes.

Implements:
1. Majority-class baseline (always predict the most common result)
2. Market-implied probability baseline (from odds)
3. Logistic Regression baseline

Evaluation metrics:
- Log Loss (primary)
- Brier Score (primary)
- Calibration (reliability)
- ROC-AUC where appropriate
- Class-specific precision/recall
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, List
from datetime import datetime


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Prediction:
    """A single match prediction with probabilistic outputs."""
    match_id: int
    p_home: float
    p_draw: float
    p_away: float
    actual_result: Optional[str] = None  # HOME, DRAW, AWAY
    prediction_time: Optional[datetime] = None

    @property
    def predicted_class(self) -> str:
        probs = {"HOME": self.p_home, "DRAW": self.p_draw, "AWAY": self.p_away}
        return max(probs, key=probs.get)

    @property
    def probability_sum(self) -> float:
        return self.p_home + self.p_draw + self.p_away


@dataclass
class EvaluationResult:
    """Results from evaluating a baseline model."""
    name: str
    log_loss: float
    brier_score: float
    accuracy: float
    n_samples: int
    class_metrics: Dict[str, Dict[str, float]]
    calibration: Optional[Dict[str, List[float]]] = None


# ---------------------------------------------------------------------------
# Odds baseline
# ---------------------------------------------------------------------------

def odds_to_market_probabilities(
    home_odds: float,
    draw_odds: float,
    away_odds: float,
) -> Tuple[float, float, float]:
    """
    Convert decimal odds to normalized market-implied probabilities.

    For decimal odds d: raw_probability = 1 / d
    overround = sum of raw probabilities
    normalized_i = raw_i / overround

    Returns:
        (p_home, p_draw, p_away) that sum to 1.0
    """
    raw_home = 1.0 / home_odds
    raw_draw = 1.0 / draw_odds
    raw_away = 1.0 / away_odds

    overround = raw_home + raw_draw + raw_away

    p_home = raw_home / overround
    p_draw = raw_draw / overround
    p_away = raw_away / overround

    return p_home, p_draw, p_away


def compute_overround(home_odds: float, draw_odds: float, away_odds: float) -> float:
    """Compute the bookmaker overround from decimal 1X2 odds."""
    return (1.0 / home_odds) + (1.0 / draw_odds) + (1.0 / away_odds)


def odds_movement_features(
    odds_snapshots: List[Dict],
) -> Dict[str, float]:
    """
    Extract odds movement features from a chronological list of odds snapshots.

    Each snapshot should have: captured_at, home_odds, draw_odds, away_odds

    Returns features:
        - opening_home_odds, opening_draw_odds, opening_away_odds
        - latest_home_odds, latest_draw_odds, latest_away_odds
        - odds_home_movement, odds_draw_movement, odds_away_movement
        - market_open_implied_home/draw/away
        - market_latest_implied_home/draw/away
        - market_open_overround, market_latest_overround
        - n_snapshots
    """
    if not odds_snapshots:
        return {}

    sorted_snaps = sorted(odds_snapshots, key=lambda x: x.get("captured_at", ""))
    first = sorted_snaps[0]
    last = sorted_snaps[-1]

    features = {
        "opening_home_odds": first["home_odds"],
        "opening_draw_odds": first["draw_odds"],
        "opening_away_odds": first["away_odds"],
        "latest_home_odds": last["home_odds"],
        "latest_draw_odds": last["draw_odds"],
        "latest_away_odds": last["away_odds"],
        "odds_home_movement": last["home_odds"] - first["home_odds"],
        "odds_draw_movement": last["draw_odds"] - first["draw_odds"],
        "odds_away_movement": last["away_odds"] - first["away_odds"],
        "n_snapshots": len(sorted_snaps),
    }

    # Implied probabilities
    oh, od, oa = odds_to_market_probabilities(
        first["home_odds"], first["draw_odds"], first["away_odds"]
    )
    lh, ld, la = odds_to_market_probabilities(
        last["home_odds"], last["draw_odds"], last["away_odds"]
    )

    features["market_open_implied_home"] = oh
    features["market_open_implied_draw"] = od
    features["market_open_implied_away"] = oa
    features["market_latest_implied_home"] = lh
    features["market_latest_implied_draw"] = ld
    features["market_latest_implied_away"] = la
    features["market_open_overround"] = compute_overround(
        first["home_odds"], first["draw_odds"], first["away_odds"]
    )
    features["market_latest_overround"] = compute_overround(
        last["home_odds"], last["draw_odds"], last["away_odds"]
    )

    return features


# ---------------------------------------------------------------------------
# Majority class baseline
# ---------------------------------------------------------------------------

class MajorityClassBaseline:
    """
    Always predict the class distribution of the training set.
    Simple but useful as a reference.
    """

    def __init__(self):
        self.class_probs_ = None
        self.classes_ = ["HOME", "DRAW", "AWAY"]

    def fit(self, y: List[str]):
        """Compute class proportions from training labels."""
        counts = {"HOME": 0, "DRAW": 0, "AWAY": 0}
        for label in y:
            counts[label] = counts.get(label, 0) + 1
        total = len(y)
        self.class_probs_ = [counts[c] / total for c in self.classes_]
        return self

    def predict_proba(self, n: int = 1) -> np.ndarray:
        """Return class probabilities for n predictions (all identical)."""
        if self.class_probs_ is None:
            raise RuntimeError("Model not fitted yet")
        return np.tile(self.class_probs_, (n, 1))


# ---------------------------------------------------------------------------
# Market baseline (already functional)
# ---------------------------------------------------------------------------

class MarketBaseline:
    """
    Use normalized market-implied probabilities as predictions.
    This is the primary baseline — bookmaker odds are hard to beat.
    """

    def predict(
        self,
        home_odds: float,
        draw_odds: float,
        away_odds: float,
    ) -> Prediction:
        p_home, p_draw, p_away = odds_to_market_probabilities(
            home_odds, draw_odds, away_odds
        )
        return Prediction(
            match_id=0,
            p_home=p_home,
            p_draw=p_draw,
            p_away=p_away,
        )


# ---------------------------------------------------------------------------
# Evaluation metrics
# ---------------------------------------------------------------------------

def log_loss(y_true: List[str], y_pred: List[Tuple[float, float, float]]) -> float:
    """
    Compute multi-class log loss.

    y_true: list of actual labels ("HOME", "DRAW", "AWAY")
    y_pred: list of (p_home, p_draw, p_away) tuples
    """
    label_to_idx = {"HOME": 0, "DRAW": 1, "AWAY": 2}
    eps = 1e-15  # clip for numerical stability

    total_loss = 0.0
    for actual, probs in zip(y_true, y_pred):
        idx = label_to_idx[actual]
        p = max(eps, min(1 - eps, probs[idx]))
        total_loss -= np.log(p)

    return total_loss / len(y_true)


def brier_score(y_true: List[str], y_pred: List[Tuple[float, float, float]]) -> float:
    """
    Compute Brier score (lower is better).

    For each sample: sum over classes of (predicted - actual)^2
    """
    label_to_idx = {"HOME": 0, "DRAW": 1, "AWAY": 2}
    total = 0.0
    for actual, probs in zip(y_true, y_pred):
        actual_vec = [0.0, 0.0, 0.0]
        actual_vec[label_to_idx[actual]] = 1.0
        for i in range(3):
            total += (probs[i] - actual_vec[i]) ** 2
    return total / len(y_true)


def accuracy(y_true: List[str], y_pred: List[Tuple[float, float, float]]) -> float:
    """Compute classification accuracy."""
    classes = ["HOME", "DRAW", "AWAY"]
    correct = 0
    for actual, probs in zip(y_true, y_pred):
        pred_idx = probs.index(max(probs))
        if classes[pred_idx] == actual:
            correct += 1
    return correct / len(y_true)


def class_precision_recall(
    y_true: List[str],
    y_pred: List[Tuple[float, float, float]],
    target_class: str,
) -> Dict[str, float]:
    """Compute precision and recall for a specific class."""
    classes = ["HOME", "DRAW", "AWAY"]
    idx = classes.index(target_class)

    tp = fp = fn = tn = 0
    for actual, probs in zip(y_true, y_pred):
        pred_idx = probs.index(max(probs))
        pred_class = classes[pred_idx]

        if actual == target_class and pred_class == target_class:
            tp += 1
        elif actual != target_class and pred_class == target_class:
            fp += 1
        elif actual == target_class and pred_class != target_class:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}


def calibration_bins(
    y_true: List[str],
    y_pred: List[Tuple[float, float, float]],
    target_class: str,
    n_bins: int = 10,
) -> Dict[str, List[float]]:
    """
    Compute calibration data for a target class.
    Returns bin_centers and observed_frequencies.
    """
    classes = ["HOME", "DRAW", "AWAY"]
    idx = classes.index(target_class)

    # Collect (predicted_prob, actual) pairs
    pairs = []
    for actual, probs in zip(y_true, y_pred):
        actual_int = 1.0 if actual == target_class else 0.0
        pairs.append((probs[idx], actual_int))

    pairs.sort(key=lambda x: x[0])

    # Bin the predictions
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_centers = []
    observed_freqs = []

    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        bin_pairs = [(p, a) for p, a in pairs if lo <= p < hi]
        if i == n_bins - 1:  # include right edge for last bin
            bin_pairs = [(p, a) for p, a in pairs if lo <= p <= hi]

        if bin_pairs:
            mean_pred = np.mean([p for p, _ in bin_pairs])
            mean_actual = np.mean([a for _, a in bin_pairs])
            bin_centers.append(mean_pred)
            observed_freqs.append(mean_actual)
        else:
            bin_centers.append((lo + hi) / 2)
            observed_freqs.append(float("nan"))

    return {"bin_centers": bin_centers, "observed_frequencies": observed_freqs}


def evaluate_baseline(
    name: str,
    y_true: List[str],
    y_pred: List[Tuple[float, float, float]],
) -> EvaluationResult:
    """Run all evaluation metrics on a set of predictions."""
    ll = log_loss(y_true, y_pred)
    bs = brier_score(y_true, y_pred)
    acc = accuracy(y_true, y_pred)

    class_metrics = {}
    for cls in ["HOME", "DRAW", "AWAY"]:
        class_metrics[cls] = class_precision_recall(y_true, y_pred, cls)

    # Calibration for each class
    cal = {}
    for cls in ["HOME", "DRAW", "AWAY"]:
        cal[cls] = calibration_bins(y_true, y_pred, cls)

    return EvaluationResult(
        name=name,
        log_loss=ll,
        brier_score=bs,
        accuracy=acc,
        n_samples=len(y_true),
        class_metrics=class_metrics,
        calibration=cal,
    )


# ---------------------------------------------------------------------------
# Feature engineering (minimal, for later use)
# ---------------------------------------------------------------------------

def build_match_features(
    match_row: Dict,
    home_ranking: Optional[Dict] = None,
    away_ranking: Optional[Dict] = None,
    home_form: Optional[List[str]] = None,
    away_form: Optional[List[str]] = None,
    odds_features: Optional[Dict] = None,
) -> Dict[str, float]:
    """
    Build a minimal feature vector for a match.

    This is intentionally simple — do NOT overengineer features yet.
    Priority:
    1. Pre-match odds
    2. Odds movement
    3. Team identity (home/away)
    4. Ranking (points, position)
    5. Historical results
    6. Recent form
    """
    features = {}

    # --- Odds features (highest priority) ---
    if odds_features:
        features.update(odds_features)
    elif "home_odds" in match_row:
        p_home, p_draw, p_away = odds_to_market_probabilities(
            match_row["home_odds"],
            match_row["draw_odds"],
            match_row["away_odds"],
        )
        features["implied_home_prob"] = p_home
        features["implied_draw_prob"] = p_draw
        features["implied_away_prob"] = p_away
        features["overround"] = compute_overround(
            match_row["home_odds"],
            match_row["draw_odds"],
            match_row["away_odds"],
        )

    # --- Ranking features ---
    if home_ranking:
        features["home_rank"] = home_ranking.get("rank", 0)
        features["home_points"] = home_ranking.get("points", 0)
    if away_ranking:
        features["away_rank"] = away_ranking.get("rank", 0)
        features["away_points"] = away_ranking.get("points", 0)

    if home_ranking and away_ranking:
        features["rank_diff"] = (
            home_ranking.get("rank", 0) - away_ranking.get("rank", 0)
        )
        features["points_diff"] = (
            home_ranking.get("points", 0) - away_ranking.get("points", 0)
        )

    # --- Form features ---
    form_map = {"Won": 1, "Draw": 0, "Lost": -1}
    if home_form:
        features["home_form_points"] = sum(
            form_map.get(f, 0) for f in home_form[:5]
        )
        features["home_form_wins"] = sum(1 for f in home_form[:5] if f == "Won")
    if away_form:
        features["away_form_points"] = sum(
            form_map.get(f, 0) for f in away_form[:5]
        )
        features["away_form_wins"] = sum(1 for f in away_form[:5] if f == "Won")

    # --- Identity ---
    features["is_home"] = 1.0  # always home perspective

    return features
