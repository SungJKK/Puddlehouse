import pytest


# ── T3: Snapshot Versioning ───────────────────────────────────────────────────

@pytest.fixture()
def table(catalog):
    catalog.register_table("bronze", "events")
    return "bronze.events"


def _files(n=2):
    return [
        {"file_path": f"/tmp/f{i}.parquet", "row_count": 100 * i, "byte_size": 1024 * i}
        for i in range(1, n + 1)
    ]


class TestCreateSnapshot:
    def test_returns_snapshot_id_version_and_file_map(self, catalog, table):
        snapshot_id, version, file_id_map = catalog.create_snapshot(
            table, files=_files(2), row_count=200, byte_size=2048
        )

        assert isinstance(snapshot_id, str) and len(snapshot_id) == 36
        assert version == 1
        assert set(file_id_map.keys()) == {"/tmp/f1.parquet", "/tmp/f2.parquet"}
        assert all(isinstance(v, str) and len(v) == 36 for v in file_id_map.values())

    def test_first_snapshot_is_version_1(self, catalog, table):
        _, version, _ = catalog.create_snapshot(table, files=_files(1), row_count=100, byte_size=1024)
        assert version == 1

    def test_version_auto_increments(self, catalog, table):
        _, v1, _ = catalog.create_snapshot(table, files=_files(1), row_count=100, byte_size=1024)
        _, v2, _ = catalog.create_snapshot(table, files=_files(1), row_count=100, byte_size=1024)
        _, v3, _ = catalog.create_snapshot(table, files=_files(1), row_count=100, byte_size=1024)

        assert v1 == 1
        assert v2 == 2
        assert v3 == 3

    def test_versions_independent_across_tables(self, catalog):
        catalog.register_table("bronze", "users")
        catalog.register_table("bronze", "orders")

        _, v_users, _ = catalog.create_snapshot("bronze.users", _files(1), 100, 1024)
        _, v_orders, _ = catalog.create_snapshot("bronze.orders", _files(1), 100, 1024)
        _, v_users2, _ = catalog.create_snapshot("bronze.users", _files(1), 100, 1024)

        assert v_users == 1
        assert v_orders == 1
        assert v_users2 == 2

    def test_snapshot_stores_row_count_and_byte_size(self, catalog, table):
        snapshot_id, _, _ = catalog.create_snapshot(table, _files(1), row_count=42, byte_size=999)
        snap = catalog.get_latest_snapshot(table)

        assert snap.row_count == 42
        assert snap.byte_size == 999

    def test_snapshot_updates_table_row_count(self, catalog, table):
        catalog.create_snapshot(table, _files(1), row_count=77, byte_size=512)
        tbl = catalog.get_table(table)
        assert tbl.row_count == 77

    def test_file_ids_are_unique_across_snapshots(self, catalog, table):
        _, _, map1 = catalog.create_snapshot(table, _files(2), 200, 2048)
        _, _, map2 = catalog.create_snapshot(table, _files(2), 200, 2048)

        all_ids = list(map1.values()) + list(map2.values())
        assert len(all_ids) == len(set(all_ids))


class TestGetLatestSnapshot:
    def test_returns_none_when_no_snapshots(self, catalog, table):
        assert catalog.get_latest_snapshot(table) is None

    def test_returns_highest_version(self, catalog, table):
        catalog.create_snapshot(table, _files(1), 100, 1024)
        catalog.create_snapshot(table, _files(1), 200, 2048)
        catalog.create_snapshot(table, _files(1), 300, 4096)

        snap = catalog.get_latest_snapshot(table)
        assert snap.version == 3
        assert snap.row_count == 300

    def test_snapshot_id_matches_last_committed(self, catalog, table):
        sid, _, _ = catalog.create_snapshot(table, _files(1), 100, 1024)
        snap = catalog.get_latest_snapshot(table)
        assert snap.snapshot_id == sid


class TestGetSnapshotFiles:
    def test_returns_all_files_for_snapshot(self, catalog, table):
        sid, _, _ = catalog.create_snapshot(table, _files(3), 300, 3072)
        files = catalog.get_snapshot_files(sid)

        assert len(files) == 3
        assert {f.file_path for f in files} == {"/tmp/f1.parquet", "/tmp/f2.parquet", "/tmp/f3.parquet"}

    def test_files_scoped_to_snapshot(self, catalog, table):
        sid1, _, _ = catalog.create_snapshot(table, [{"file_path": "/tmp/a.parquet", "row_count": 10, "byte_size": 100}], 10, 100)
        sid2, _, _ = catalog.create_snapshot(table, [{"file_path": "/tmp/b.parquet", "row_count": 20, "byte_size": 200}], 20, 200)

        files1 = catalog.get_snapshot_files(sid1)
        files2 = catalog.get_snapshot_files(sid2)

        assert [f.file_path for f in files1] == ["/tmp/a.parquet"]
        assert [f.file_path for f in files2] == ["/tmp/b.parquet"]

    def test_file_metadata_stored_correctly(self, catalog, table):
        sid, _, _ = catalog.create_snapshot(
            table,
            [{"file_path": "/tmp/x.parquet", "row_count": 55, "byte_size": 777}],
            55, 777
        )
        files = catalog.get_snapshot_files(sid)

        assert files[0].row_count == 55
        assert files[0].byte_size == 777
        assert files[0].table_id == table

    def test_returns_empty_for_unknown_snapshot(self, catalog):
        files = catalog.get_snapshot_files("nonexistent-id")
        assert files == []
