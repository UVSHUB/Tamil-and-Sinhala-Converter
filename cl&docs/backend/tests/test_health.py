from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health_endpoint():
    """
    Verifies that the REST health check endpoint is operational, 
    returns a 200 OK status, and returns the expected service metadata.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "voice-translator-backend"
    assert "gemini_live_configured" in data
