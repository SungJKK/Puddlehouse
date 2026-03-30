RECORDS = [{"user_id": "u001", "score": 10}]

VIEW_BODY = {
    "name": "top_users",
    "zone": "gold",
    "view_type": "view",
    "sql": "SELECT user_id FROM bronze_users",
    "owner": "analytics",
}

MAT_VIEW_BODY = {
    "name": "user_summary",
    "zone": "gold",
    "view_type": "materialized_view",
    "sql": "SELECT user_id, score FROM bronze_users",
    "owner": "analytics",
}


def test_register_and_list_views(api_client):
    r = api_client.post("/api/v1/views", json=VIEW_BODY)
    assert r.status_code == 201
    assert "view_id" in r.json()

    r = api_client.get("/api/v1/views")
    assert r.status_code == 200
    names = [v["name"] for v in r.json()["views"]]
    assert "top_users" in names


def test_list_views_filter_by_zone(api_client):
    api_client.post("/api/v1/views", json=VIEW_BODY)
    api_client.post("/api/v1/views", json={**VIEW_BODY, "name": "other", "zone": "silver"})
    r = api_client.get("/api/v1/views?zone=gold")
    assert r.status_code == 200
    assert all(v["zone"] == "gold" for v in r.json()["views"])


def test_list_views_filter_by_type(api_client):
    api_client.post("/api/v1/views", json=VIEW_BODY)
    api_client.post("/api/v1/views", json=MAT_VIEW_BODY)
    r = api_client.get("/api/v1/views?type=materialized_view")
    assert r.status_code == 200
    assert all(v["view_type"] == "materialized_view" for v in r.json()["views"])


def test_get_view(api_client):
    view_id = api_client.post("/api/v1/views", json=VIEW_BODY).json()["view_id"]
    r = api_client.get(f"/api/v1/views/{view_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["view_id"] == view_id
    assert body["name"] == "top_users"


def test_refresh_materialized_view(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    snap_id = api_client.get("/api/v1/tables/bronze/users/snapshots/latest").json()["snapshot_id"]
    view_id = api_client.post("/api/v1/views", json=MAT_VIEW_BODY).json()["view_id"]

    r = api_client.post(f"/api/v1/views/{view_id}/refresh", json={"snapshot_id": snap_id})
    assert r.status_code == 200
    body = r.json()
    assert body["refresh_snapshot_id"] == snap_id
    assert body["last_refreshed_at"] is not None


# ── Error paths ───────────────────────────────────────────────────────

def test_get_view_not_found(api_client):
    r = api_client.get("/api/v1/views/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_refresh_plain_view_fails(api_client):
    view_id = api_client.post("/api/v1/views", json=VIEW_BODY).json()["view_id"]
    r = api_client.post(f"/api/v1/views/{view_id}/refresh", json={"snapshot_id": "snap_123"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
