from redact import redact

def test_redact_sensitive_keys_and_proxy_url():
    value = redact({"access_token": "x", "api_key": "y", "password": "z", "proxy": "http://u:p@host:80"})
    assert all(v == "[REDACTED]" for v in value.values())
