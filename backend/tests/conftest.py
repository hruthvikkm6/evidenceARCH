import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db
@pytest.fixture(autouse=True)
def reset_db(tmp_path):
    from app.core import config
    config.settings.database_path=str(tmp_path/"test.db")
    config.settings.storage_path=str(tmp_path/"evidence")
    init_db()
    yield
@pytest.fixture
def client():
    with TestClient(app) as c:
        result=c.post("/api/v1/auth/signup",json={"full_name":"Test Investigator","email":"workflow@example.com","password":"SecureTestPass123"})
        assert result.status_code==201,result.text
        yield c
