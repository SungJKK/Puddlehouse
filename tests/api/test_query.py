RECORDS = [{"user_id": "u001", "score": 10}, {"user_id": "u002", "score": 20}]


def test_query_basic(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/query", json={
        "sql": "SELECT user_id, score FROM bronze_users ORDER BY score",
        "context": {"zone": "bronze", "entity": "users"},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["columns"] == ["user_id", "score"]
    assert body["row_count"] == 2
    assert body["version_used"] == 1


def test_query_aggregation(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/query", json={
        "sql": "SELECT COUNT(*) AS total FROM bronze_users",
        "context": {"zone": "bronze", "entity": "users"},
    })
    assert r.status_code == 200
    assert r.json()["rows"][0][0] == 2


def test_query_time_travel(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/query", json={
        "sql": "SELECT COUNT(*) AS n FROM bronze_users",
        "context": {"zone": "bronze", "entity": "users", "version": 1},
    })
    assert r.status_code == 200
    assert r.json()["version_used"] == 1


# ── Error paths ───────────────────────────────────────────────────────

def test_query_invalid_sql(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/query", json={
        "sql": "SELECT ??? INVALID SQL",
        "context": {"zone": "bronze", "entity": "users"},
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_SQL"


def test_query_table_not_found(api_client):
    r = api_client.post("/api/v1/query", json={
        "sql": "SELECT * FROM bronze_ghost",
        "context": {"zone": "bronze", "entity": "ghost"},
    })
    assert r.status_code == 404


def test_query_version_not_found(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/query", json={
        "sql": "SELECT * FROM bronze_users",
        "context": {"zone": "bronze", "entity": "users", "version": 999},
    })
    assert r.status_code == 404
