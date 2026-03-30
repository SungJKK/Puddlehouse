RECORDS = [{"user_id": "u001", "score": 10}, {"user_id": "u002", "score": 20}]


def test_get_table_stats(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["table_id"] == "bronze.users"
    col_names = [s["name"] for s in body["column_stats"]]
    assert "user_id" in col_names
    assert "score" in col_names


def test_get_file_stats(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/stats/files")
    assert r.status_code == 200
    body = r.json()
    assert body["table_id"] == "bronze.users"
    assert len(body["file_stats"]) >= 1
    first_file = body["file_stats"][0]
    assert "file_id" in first_file
    assert "file_path" in first_file
    assert len(first_file["column_stats"]) >= 1


def test_stats_empty_table(api_client):
    r = api_client.get("/api/v1/tables/bronze/ghost/stats")
    assert r.status_code == 200
    assert r.json()["column_stats"] == []
