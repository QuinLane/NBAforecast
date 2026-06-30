"""M2 vertical-slice smoke test — proves the full spine is wired (T2.17).

DB seeding → feature engineering → LightGBM prediction → TreeSHAP explanation
→ feature humanizer → FastAPI response. Exercises the complete path with a
real (tiny) trained model and an in-memory SQLite database.

Browser E2E (load /games/{id} in a real browser, verify PredictionExplainer
renders the top-5 drivers) requires a running stack and is deferred to the M4/M5
testing-hardening milestone.
"""

import math

from fastapi.testclient import TestClient


def test_full_spine_game_to_explained_prediction(client: TestClient, sample_game_id: str) -> None:
    """Games list → game detail → prediction with additive Explanation."""
    # 1. Games list is non-empty.
    games = client.get("/api/v1/games").json()
    assert games["total"] > 0

    # 2. Single game is reachable.
    game = client.get(f"/api/v1/games/{sample_game_id}").json()
    assert game["game_id"] == sample_game_id

    # 3. Prediction endpoint returns a calibrated probability in [0, 1].
    pred = client.get(f"/api/v1/games/{sample_game_id}/prediction").json()
    assert 0.0 <= pred["win_prob"] <= 1.0

    # 4. Explanation is present with correct shape: top-5 truncated, humanizer ran.
    exp = pred["explanation"]
    assert exp["units"] == "probability_points"
    assert len(exp["contributions"]) <= 5
    for contrib in exp["contributions"]:
        assert contrib["display_label"] != contrib["feature"], (
            "humanizer must rename every feature in the API response"
        )
        assert contrib["direction"] in {"up", "down"}


def test_shap_additivity_through_api(client: TestClient, sample_game_id: str) -> None:
    """sum(contributions) ≈ prediction - baseline in the full-explanation endpoint.

    This is the SHAP honesty invariant (explainability.md §8) verified through
    the HTTP layer, complementing the unit-level additivity test in
    tests/ml/test_shap_additivity.py.
    """
    resp = client.get(f"/api/v1/games/{sample_game_id}/prediction/full-explanation")
    assert resp.status_code == 200
    exp = resp.json()["explanation"]

    contribution_sum = sum(c["contribution"] for c in exp["contributions"])
    expected_delta = exp["prediction"] - exp["baseline"]
    assert math.isclose(contribution_sum, expected_delta, abs_tol=1e-4), (
        f"SHAP additivity broken through API: sum={contribution_sum:.6f}, "
        f"prediction-baseline={expected_delta:.6f}, "
        f"diff={abs(contribution_sum - expected_delta):.6f}"
    )


def test_404_error_envelope_shape(client: TestClient) -> None:
    """Unknown game IDs return a typed error envelope, not an unhandled 500."""
    resp = client.get("/api/v1/games/does-not-exist/prediction")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body) == {"error", "detail"}
    assert "does-not-exist" in body["detail"]
