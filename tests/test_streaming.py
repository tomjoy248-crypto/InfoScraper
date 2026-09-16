from streaming import process_rows


def test_dedup_keys_do_not_filter_when_dedup_disabled():
    rows = [{"id": "1"}, {"id": "1"}, {"id": "2"}]
    assert list(process_rows(rows, dedup_keys=["id"], known_keys={("1",)}, dedup=False)) == rows


def test_incremental_keys_filter_when_enabled():
    rows = [{"id": "1"}, {"id": "2"}, {"id": "2"}]
    assert list(process_rows(rows, dedup_keys=["id"], known_keys={("1",)}, dedup=True)) == [{"id": "2"}]
