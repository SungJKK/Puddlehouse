RECORDS = [{"user_id": "u001", "name": "Alice"}, {"user_id": "u002", "name": "Bob"}]


def test_list_tables_empty(api_client):
    r = api_client.get("/api/v1/tables")
    assert r.status_code == 200
    assert r.json()["tables"] == []


def test_list_tables_with_data(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables")
    assert r.status_code == 200
    ids = [t["table_id"] for t in r.json()["tables"]]
    assert "bronze.users" in ids


def test_list_tables_zone_filter(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/silver/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables?zone=silver")
    assert r.status_code == 200
    assert all(t["zone"] == "silver" for t in r.json()["tables"])


def test_get_table(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users")
    assert r.status_code == 200
    body = r.json()
    assert body["table_id"] == "bronze.users"
    assert body["latest_version"] == 1
    assert body["row_count"] == 2


def test_deregister_table(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.delete("/api/v1/tables/bronze/users")
    assert r.status_code == 204
    # Table should no longer appear in list
    tables = api_client.get("/api/v1/tables").json()["tables"]
    assert not any(t["table_id"] == "bronze.users" for t in tables)


# ── Error paths ───────────────────────────────────────────────────────

def test_get_table_not_found(api_client):
    r = api_client.get("/api/v1/tables/bronze/nonexistent")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_deregister_table_not_found(api_client):
    r = api_client.delete("/api/v1/tables/bronze/ghost")
    assert r.status_code == 404
