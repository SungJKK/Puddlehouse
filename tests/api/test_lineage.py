RECORDS = [{"user_id": "u001", "score": 10}]


def test_record_and_get_lineage(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/tables/bronze/users/lineage", json={
        "source_id": "external:kafka",
        "job_name": "ingest_job",
        "run_id": "run_001",
        "rows_read": 500,
        "rows_written": 1,
    })
    assert r.status_code == 201
    assert "lineage_id" in r.json()

    r = api_client.get("/api/v1/tables/bronze/users/lineage")
    assert r.status_code == 200
    body = r.json()
    assert body["table_id"] == "bronze.users"
    upstream = body["upstream"]
    assert any(e["source_id"] == "external:kafka" for e in upstream)


def test_lineage_direction_downstream(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/lineage", json={"source_id": "external:src"})
    r = api_client.get("/api/v1/tables/bronze/users/lineage?direction=downstream")
    assert r.status_code == 200
    body = r.json()
    assert body["upstream"] == []


def test_lineage_direction_upstream(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/lineage", json={"source_id": "external:src"})
    r = api_client.get("/api/v1/tables/bronze/users/lineage?direction=upstream")
    assert r.status_code == 200
    assert r.json()["downstream"] == []
