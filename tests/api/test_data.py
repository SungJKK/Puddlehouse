RECORDS = [{"user_id": "u001", "score": 10}, {"user_id": "u002", "score": 20}]


def test_write_data(api_client):
    r = api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    assert r.status_code == 201
    body = r.json()
    assert body["version"] == 1
    assert body["row_count"] == 2
    assert body["files_written"] >= 1
    assert body["byte_size"] > 0


def test_read_data(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/data")
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 2
    assert "user_id" in body["columns"]
    assert len(body["rows"]) == 2


def test_read_data_pagination(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/data?limit=1&offset=0")
    assert r.status_code == 200
    assert r.json()["row_count"] == 1


def test_read_data_at_version(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/data?version=1")
    assert r.status_code == 200
    assert r.json()["version"] == 1


def test_compact(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/tables/bronze/users/compact")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 3
    assert body["files_merged"] >= 1
    assert body["row_count"] == 4


# ── Error paths ───────────────────────────────────────────────────────

def test_write_schema_evolution_violation(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    # Drop existing column — should be rejected
    r = api_client.post("/api/v1/tables/bronze/users/data",
                        json={"records": [{"user_id": "u003"}]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SCHEMA_EVOLUTION_ERROR"
