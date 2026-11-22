"""HTTP API tests for the user routes: FastAPI + Pydantic + real PostgreSQL.

Covers POST /users/register, POST /users/login, GET /users/me and
GET /users/{id}.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth.security import verify_password
from app.auth.tokens import create_access_token, decode_access_token
from app.config import get_settings
from app.models import User

pytestmark = pytest.mark.integration

PAYLOAD = {"username": "erin", "email": "erin@example.com", "password": "Secret123"}


def register(client, **overrides):
    return client.post("/users/register", json={**PAYLOAD, **overrides})


def login(client, username="erin", password="Secret123"):
    return client.post("/users/login", json={"username": username, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ----- POST /users/register ---------------------------------------------------


def test_register_returns_user_without_password(client):
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "erin"
    assert body["email"] == "erin@example.com"
    assert "created_at" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_register_stores_only_a_bcrypt_hash(client, db_session):
    register(client)

    user = db_session.scalar(select(User).where(User.username == "erin"))
    assert user.password_hash != "Secret123"
    assert user.password_hash.startswith("$2b$")
    assert verify_password("Secret123", user.password_hash)


def test_register_normalizes_username_and_email(client):
    body = register(client, username="  Erin  ", email="Erin@Example.COM").json()
    assert body["username"] == "erin"
    assert body["email"] == "erin@example.com"


def test_register_duplicate_username_returns_409(client):
    assert register(client).status_code == 201

    response = register(client, email="another@example.com")
    assert response.status_code == 409
    assert response.json()["detail"] == "Username or email already registered"


def test_register_duplicate_email_is_case_insensitive(client):
    assert register(client).status_code == 201

    response = register(client, username="erin2", email="ERIN@Example.com")
    assert response.status_code == 409


def test_register_invalid_email_returns_422(client):
    response = register(client, email="not-an-email")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "email"]


@pytest.mark.parametrize(
    "password",
    ["weakpass", "Short1", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere", "A1" + "a" * 71],
)
def test_register_weak_or_too_long_password_returns_422(client, password):
    response = register(client, password=password)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "password"]


@pytest.mark.parametrize("username", ["ab", "has space", "bad!chars", "x" * 51])
def test_register_invalid_username_returns_422(client, username):
    assert register(client, username=username).status_code == 422


@pytest.mark.parametrize("missing", ["username", "email", "password"])
def test_register_missing_field_returns_422(client, missing):
    payload = {key: value for key, value in PAYLOAD.items() if key != missing}
    response = client.post("/users/register", json=payload)
    assert response.status_code == 422


def test_old_register_route_is_gone(client):
    assert client.post("/users", json=PAYLOAD).status_code == 404


# ----- POST /users/login ----------------------------------------------------------


def test_login_returns_bearer_token(client):
    user_id = register(client).json()["id"]

    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert body["user"]["id"] == user_id
    assert "password_hash" not in body["user"]
    assert str(decode_access_token(body["access_token"])) == user_id


def test_login_with_email_and_any_case(client):
    register(client)

    assert login(client, username="ERIN@example.com").status_code == 200
    assert login(client, username="  Erin ").status_code == 200


def test_login_wrong_password_returns_401(client):
    register(client)

    response = login(client, password="Wrong1234")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_password_is_case_sensitive(client):
    register(client)
    assert login(client, password="secret123").status_code == 401


def test_login_unknown_user_gives_same_401(client):
    register(client)

    unknown = login(client, username="nobody")
    wrong_password = login(client, password="Wrong1234")

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json()


@pytest.mark.parametrize(
    "payload",
    [{}, {"username": "erin"}, {"password": "Secret123"}, {"username": "", "password": "x"}],
)
def test_login_missing_fields_returns_422(client, payload):
    assert client.post("/users/login", json=payload).status_code == 422


# ----- GET /users/me (token required) -------------------------------------------


def test_me_with_token_returns_current_user(client):
    register(client)
    token = login(client).json()["access_token"]

    response = client.get("/users/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["username"] == "erin"
    assert "password_hash" not in response.json()


def test_me_without_token_returns_401(client):
    response = client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c", ""])
def test_me_with_garbage_token_returns_401(client, token):
    assert client.get("/users/me", headers=bearer(token)).status_code == 401


def test_me_with_expired_token_returns_401(client):
    user_id = register(client).json()["id"]
    token = create_access_token(uuid.UUID(user_id), expires_delta=timedelta(seconds=-1))

    response = client.get("/users/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_me_for_deleted_user_returns_401(client, db_session):
    register(client)
    token = login(client).json()["access_token"]
    db_session.delete(db_session.scalar(select(User).where(User.username == "erin")))
    db_session.commit()

    response = client.get("/users/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["detail"] == "User no longer exists"


def test_me_with_wrong_scheme_returns_401(client):
    register(client)
    token = login(client).json()["access_token"]
    assert client.get("/users/me", headers={"Authorization": f"Basic {token}"}).status_code == 401


# ----- GET /users/{id} -----------------------------------------------------------


def test_get_user_by_id(client):
    user_id = register(client).json()["id"]

    response = client.get(f"/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["username"] == "erin"
    assert "password_hash" not in response.json()


def test_user_id_is_a_uuid(client):
    user_id = register(client).json()["id"]
    assert str(uuid.UUID(user_id)) == user_id


def test_get_missing_user_returns_404(client):
    assert client.get(f"/users/{uuid.uuid4()}").status_code == 404


def test_get_user_with_malformed_id_returns_422(client):
    assert client.get("/users/123").status_code == 422
