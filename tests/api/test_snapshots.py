RECORDS = [{"user_id": "u001", "score": 10}, {"user_id": "u002", "score": 20}]


def test_list_snapshots(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/snapshots")
    assert r.status_code == 200
    body = r.json()
    assert body["table_id"] == "bronze.users"
    assert len(body["snapshots"]) == 1
    assert body["snapshots"][0]["version"] == 1


def test_get_latest_snapshot(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/snapshots/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 1
    assert body["row_count"] == 2
    assert len(body["files"]) >= 1


def test_get_snapshot_at_version(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/snapshots/1")
    assert r.status_code == 200
    assert r.json()["version"] == 1


def test_multiple_snapshots_ordered(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    snaps = api_client.get("/api/v1/tables/bronze/users/snapshots").json()["snapshots"]
    versions = [s["version"] for s in snaps]
    assert versions == sorted(versions)


# ── Error paths ───────────────────────────────────────────────────────

def test_latest_snapshot_no_data(api_client):
    # Register a table without writing any data
    r = api_client.get("/api/v1/tables/bronze/empty/snapshots/latest")
    assert r.status_code == 404


def test_snapshot_version_not_found(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/snapshots/999")
    assert r.status_code == 404
