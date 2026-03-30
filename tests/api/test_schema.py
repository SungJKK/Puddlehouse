RECORDS = [{"user_id": "u001", "age": 30}, {"user_id": "u002", "age": 25}]


def test_get_schema(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/schema")
    assert r.status_code == 200
    body = r.json()
    assert body["table_id"] == "bronze.users"
    assert body["version"] == 1
    col_names = [c["name"] for c in body["columns"]]
    assert "user_id" in col_names
    assert "age" in col_names


def test_get_schema_at_version(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    # Add a new column in v2
    api_client.post("/api/v1/tables/bronze/users/data",
                    json={"records": [{"user_id": "u003", "age": 22, "email": "x@x.com"}]})
    r = api_client.get("/api/v1/tables/bronze/users/schema?version=1")
    assert r.status_code == 200
    col_names = [c["name"] for c in r.json()["columns"]]
    assert "email" not in col_names


def test_validate_schema_compatible(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    # Fetch actual stored types rather than hardcoding them (PyArrow may infer
    # "large_string" instead of "string" depending on pandas/arrow version)
    current_cols = api_client.get("/api/v1/tables/bronze/users/schema").json()["columns"]
    new_schema = [{"name": c["name"], "type": c["type"]} for c in current_cols]
    new_schema.append({"name": "email", "type": "large_string"})

    r = api_client.post("/api/v1/tables/bronze/users/schema/validate",
                        json={"schema": new_schema})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert "email" in body["added_columns"]


# ── Error paths ───────────────────────────────────────────────────────

def test_validate_schema_incompatible(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    # Remove an existing column — not allowed
    r = api_client.post("/api/v1/tables/bronze/users/schema/validate", json={
        "schema": [{"name": "user_id", "type": "string"}]
    })
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert len(body["errors"]) > 0


def test_get_schema_no_snapshots(api_client):
    r = api_client.get("/api/v1/tables/bronze/ghost/schema")
    assert r.status_code == 404
