RECORDS = [{"user_id": "u001", "score": 10}]


def test_register_and_list_partitions(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/tables/bronze/users/partitions", json={
        "key": "date",
        "value": "2026-01-01",
        "file_path": "warehouse/bronze/users/date=2026-01-01/part-0.parquet",
        "row_count": 100,
    })
    assert r.status_code == 201
    assert "partition_id" in r.json()

    r = api_client.get("/api/v1/tables/bronze/users/partitions")
    assert r.status_code == 200
    parts = r.json()["partitions"]
    assert len(parts) >= 1
    assert parts[0]["key"] == "date"
    assert parts[0]["value"] == "2026-01-01"


def test_list_partitions_empty(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/partitions")
    assert r.status_code == 200
    assert r.json()["partitions"] == []
