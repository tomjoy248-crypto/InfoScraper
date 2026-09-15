from subdomain import brute_subdomains


def test_wildcard_requires_three_consistent_probes(monkeypatch):
    values = iter(["1.1.1.1", "1.1.1.1", "2.2.2.2", "1.1.1.1", "1.1.1.1"])
    monkeypatch.setattr("subdomain.dns_resolve", lambda host, timeout: next(values))
    rows = brute_subdomains("example.com", wordlist=["www"], threads=1)
    assert rows


def test_stable_wildcard_filters_matching_ip(monkeypatch):
    values = iter(["1.1.1.1", "1.1.1.1", "1.1.1.1", "1.1.1.1"])
    monkeypatch.setattr("subdomain.dns_resolve", lambda host, timeout: next(values))
    assert brute_subdomains("example.com", wordlist=["www"], threads=1) == []
