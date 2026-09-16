import database


def use_temp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "proxy.db"))


def test_duplicate_proxy_is_not_inserted(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    address = "http://u:p@127.0.0.1:8080"
    database.add_proxy(address)
    database.add_proxy(address)
    assert [p["address"] for p in database.list_proxies()] == [address]


def test_encrypted_proxy_can_be_disabled_and_enabled(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    address = "http://u:p@127.0.0.1:8080"
    database.add_proxy(address)
    database.set_proxy_enabled(address, False)
    assert database.list_proxies()[0]["enabled"] is False
    database.set_proxy_enabled(address, True)
    assert database.list_proxies()[0]["enabled"] is True


def test_encrypted_proxy_success_resets_failures(monkeypatch, tmp_path):
    use_temp_db(monkeypatch, tmp_path)
    address = "http://u:p@127.0.0.1:8080"
    database.add_proxy(address)
    database.mark_proxy_fail(address)
    assert database.list_proxies()[0]["fail_count"] == 1
    database.mark_proxy_success(address)
    proxy = database.list_proxies()[0]
    assert proxy["fail_count"] == 0 and proxy["enabled"] is True
