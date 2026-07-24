def test_grafana_proxy_requires_auth(client):
    resp = client.get("/api/grafana/d/some-uid/some-dashboard")
    assert resp.status_code == 401
