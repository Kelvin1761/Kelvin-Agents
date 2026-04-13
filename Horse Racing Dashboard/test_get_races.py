from fastapi.testclient import TestClient
import sys
sys.path.append('backend')
from main import app

client = TestClient(app)
response = client.get("/api/meetings/2026-04-02/Gosford/races")
races_by_analyst = response.json().get('races_by_analyst', {})
print("Kelvin races:", [r['race_number'] for r in races_by_analyst.get('Kelvin', [])])
