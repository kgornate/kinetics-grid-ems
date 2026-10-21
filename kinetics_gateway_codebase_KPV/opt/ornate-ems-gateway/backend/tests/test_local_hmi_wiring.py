from fastapi.testclient import TestClient


def test_hmi_router_integrated():
    from app.main import app
    client = TestClient(app)
    for path, mime in [('/hmi/', 'text/html'),('/hmi/styles.css','text/css'),('/hmi/app.js','text/javascript')]:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text[:200])
        assert mime in r.headers['content-type']
    assert client.get('/hmi').status_code in (200, 307)
