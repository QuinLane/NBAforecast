"""Contract tests for the games + predictions router (backend-api.md Prompt 8).

Verifies status codes, response shape, pagination, and the error envelope against a seeded
in-memory database and a real (if tiny) trained model — see conftest.py for how.
"""

from fastapi.testclient import TestClient


def test_health_is_ok() -> None:
    from nbaforecast.api.main import app

    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── GET /api/v1/games ────────────────────────────────────────────────────────────────────────────


def test_list_games_returns_a_page_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/games")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert body["total"] > 0
    assert len(body["items"]) == min(body["total"], 25)


def test_list_games_item_shape(client: TestClient) -> None:
    body = client.get("/api/v1/games").json()
    item = body["items"][0]
    assert set(item) == {
        "game_id",
        "season",
        "game_date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "status",
    }
    assert set(item["home_team"]) == {"team_id", "abbreviation", "full_name"}


def test_list_games_pagination_respects_page_size(client: TestClient) -> None:
    response = client.get("/api/v1/games", params={"page_size": 5})
    body = response.json()
    assert body["page_size"] == 5
    assert len(body["items"]) == 5


def test_list_games_pagination_second_page_differs_from_first(client: TestClient) -> None:
    page_1 = client.get("/api/v1/games", params={"page_size": 5, "page": 1}).json()
    page_2 = client.get("/api/v1/games", params={"page_size": 5, "page": 2}).json()
    ids_1 = {item["game_id"] for item in page_1["items"]}
    ids_2 = {item["game_id"] for item in page_2["items"]}
    assert ids_1.isdisjoint(ids_2)


def test_list_games_filters_by_team(client: TestClient) -> None:
    body = client.get("/api/v1/games", params={"team": 1, "page_size": 100}).json()
    assert body["total"] > 0
    for item in body["items"]:
        assert item["home_team"]["team_id"] == 1 or item["away_team"]["team_id"] == 1


def test_list_games_filters_by_season(client: TestClient) -> None:
    all_games = client.get("/api/v1/games", params={"page_size": 200}).json()
    season = all_games["items"][0]["season"]
    filtered = client.get("/api/v1/games", params={"season": season, "page_size": 200}).json()
    assert filtered["total"] > 0
    assert all(item["season"] == season for item in filtered["items"])


# ── GET /api/v1/games/{game_id} ──────────────────────────────────────────────────────────────────


def test_get_game_returns_full_detail(client: TestClient, sample_game_id: str) -> None:
    response = client.get(f"/api/v1/games/{sample_game_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["game_id"] == sample_game_id
    assert set(body) >= {
        "game_id",
        "season",
        "game_date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "status",
        "game_datetime",
        "num_periods",
    }


def test_get_game_404_for_unknown_id_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/games/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error", "detail"}
    assert "does-not-exist" in body["detail"]


# ── GET /api/v1/games/{game_id}/prediction ──────────────────────────────────────────────────────


def test_get_game_prediction_shape(client: TestClient, sample_game_id: str) -> None:
    response = client.get(f"/api/v1/games/{sample_game_id}/prediction")
    assert response.status_code == 200
    body = response.json()
    assert body["game_id"] == sample_game_id
    assert 0.0 <= body["win_prob"] <= 1.0
    assert body["margin"] is None
    assert body["total"] is None
    assert body["market"] is None


def test_get_game_prediction_explanation_shape(client: TestClient, sample_game_id: str) -> None:
    body = client.get(f"/api/v1/games/{sample_game_id}/prediction").json()
    explanation = body["explanation"]
    assert set(explanation) == {"baseline", "prediction", "contributions", "units", "notes"}
    assert explanation["units"] == "probability_points"
    assert explanation["prediction"] == body["win_prob"]


def test_get_game_prediction_top_5_drivers_only(client: TestClient, sample_game_id: str) -> None:
    body = client.get(f"/api/v1/games/{sample_game_id}/prediction").json()
    assert len(body["explanation"]["contributions"]) <= 5


def test_get_game_prediction_contributions_are_humanized(
    client: TestClient, sample_game_id: str
) -> None:
    body = client.get(f"/api/v1/games/{sample_game_id}/prediction").json()
    for contribution in body["explanation"]["contributions"]:
        assert set(contribution) == {
            "feature",
            "display_label",
            "raw_value",
            "formatted_value",
            "contribution",
            "direction",
        }
        # The humanizer always sets a real label distinct from the raw feature name.
        assert contribution["display_label"] != contribution["feature"]
        assert contribution["direction"] in {"up", "down"}


def test_get_game_prediction_full_explanation_has_more_contributions(
    client: TestClient, sample_game_id: str
) -> None:
    top5 = client.get(f"/api/v1/games/{sample_game_id}/prediction").json()
    full = client.get(f"/api/v1/games/{sample_game_id}/prediction/full-explanation").json()
    assert len(full["explanation"]["contributions"]) >= len(top5["explanation"]["contributions"])
    assert len(full["explanation"]["contributions"]) > 5


def test_get_game_prediction_404_for_unknown_game(client: TestClient) -> None:
    response = client.get("/api/v1/games/does-not-exist/prediction")
    assert response.status_code == 404
    assert set(response.json()) == {"error", "detail"}
