from fastapi.testclient import TestClient
from src.app import app


def test_commerce_api_requires_server_session():
    client = TestClient(app)
    assert client.get('/api/commerce/status').status_code == 401
    response = client.post('/auth/status', json={'username': 'admin', 'password': 'admin123'})
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert client.get('/api/commerce/status').status_code == 200
    client.post('/auth/logout')
    assert client.get('/api/commerce/status').status_code == 401
