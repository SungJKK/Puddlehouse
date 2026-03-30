RECORDS = [{"user_id": "u001", "score": 10}, {"user_id": "u002", "score": 20}]


def test_get_audit_log(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["table_id"] == "bronze.users"
    assert len(body["entries"]) > 0
    operations = {e["operation"] for e in body["entries"]}
    assert "SNAPSHOT" in operations


def test_audit_log_limit(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.get("/api/v1/tables/bronze/users/audit?limit=1")
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 1


def test_add_and_list_quality_contracts(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/tables/bronze/users/quality/contracts", json={
        "check_type": "not_empty",
        "params": {"min_rows": 1},
    })
    assert r.status_code == 201
    assert "contract_id" in r.json()

    r = api_client.get("/api/v1/tables/bronze/users/quality/contracts")
    assert r.status_code == 200
    contracts = r.json()["contracts"]
    assert len(contracts) == 1
    assert contracts[0]["check_type"] == "not_empty"


def test_run_quality_checks_pass(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/quality/contracts",
                    json={"check_type": "not_empty", "params": {"min_rows": 1}})
    r = api_client.post("/api/v1/tables/bronze/users/quality/run")
    assert r.status_code == 200
    body = r.json()
    assert body["all_passed"] is True
    assert body["results"][0]["passed"] is True


def test_vacuum_dry_run(api_client):
    # Write two snapshots so there is something to vacuum
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/tables/bronze/users/vacuum",
                        json={"retain_last_n": 1, "dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["snapshots_removed"] == 1
    assert body["files_removed"] >= 1
    # Dry run — files should still exist
    assert len(body["paths"]) == body["files_removed"]


def test_vacuum_executes(api_client):
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    api_client.post("/api/v1/tables/bronze/users/data", json={"records": RECORDS})
    r = api_client.post("/api/v1/tables/bronze/users/vacuum",
                        json={"retain_last_n": 1, "dry_run": False})
    assert r.status_code == 200
    assert r.json()["dry_run"] is False
    assert r.json()["files_removed"] >= 1
