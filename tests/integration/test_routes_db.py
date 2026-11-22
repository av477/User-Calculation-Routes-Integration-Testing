"""Route tests that check what actually ends up in PostgreSQL.

Each test calls the API over HTTP, then reads the tables back with plain SQL,
so the check doesn't rely on objects SQLAlchemy already has in memory.
Failing requests are checked for their status code, their error body, and
that they left the database unchanged.
"""

import uuid

import pytest
from sqlalchemy import text

from app.auth.security import verify_password
from app.auth.tokens import decode_access_token

pytestmark = pytest.mark.integration

USER = {"username": "dbcheck", "email": "dbcheck@example.com", "password": "Secret123"}


def user_row(db, username):
    return db.execute(
        text("SELECT id, username, email, password_hash, created_at FROM users WHERE username = :u"),
        {"u": username},
    ).mappings().one_or_none()


def calculation_row(db, calculation_id):
    return db.execute(
        text("SELECT id, user_id, type, a, b, result FROM calculations WHERE id = :id"),
        {"id": uuid.UUID(calculation_id)},
    ).mappings().one_or_none()


def count(db, table):
    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


@pytest.fixture
def user_id(client):
    response = client.post("/users/register", json=USER)
    assert response.status_code == 201
    return response.json()["id"]


# ----- Users: register, login, verify in DB ------------------------------------


def test_register_writes_user_row(client, db_session):
    response = client.post(
        "/users/register",
        json={"username": "NewUser", "email": "New@Example.com", "password": "Secret123"},
    )
    assert response.status_code == 201

    row = user_row(db_session, "newuser")
    assert row is not None
    assert str(row["id"]) == response.json()["id"]
    assert row["email"] == "new@example.com"
    assert row["created_at"] is not None
    # Only a bcrypt hash is stored, and it matches the password.
    assert "Secret123" not in row["password_hash"]
    assert row["password_hash"].startswith("$2b$")
    assert verify_password("Secret123", row["password_hash"])


def test_rejected_registration_writes_nothing(client, db_session, user_id):
    before = count(db_session, "users")

    duplicate = client.post("/users/register", json={**USER, "email": "x@example.com"})
    invalid = client.post("/users/register", json={**USER, "username": "zz"})

    assert (duplicate.status_code, invalid.status_code) == (409, 422)
    assert count(db_session, "users") == before


def test_login_token_points_at_the_stored_user(client, db_session, user_id):
    response = client.post(
        "/users/login", json={"username": USER["username"], "password": USER["password"]}
    )
    assert response.status_code == 200

    token_user_id = decode_access_token(response.json()["access_token"])
    row = user_row(db_session, USER["username"])
    assert token_user_id == row["id"]
    assert response.json()["user"]["email"] == row["email"]


def test_login_does_not_change_the_stored_hash(client, db_session, user_id):
    before = user_row(db_session, USER["username"])["password_hash"]
    client.post("/users/login", json={"username": USER["username"], "password": "Wrong1234"})
    client.post("/users/login", json={"username": USER["username"], "password": "Secret123"})
    assert user_row(db_session, USER["username"])["password_hash"] == before


# ----- Calculations: create, retrieve, update, delete (checked in DB) ----------


def test_calculation_lifecycle_is_stored_in_db(client, db_session, user_id):
    # Create
    created = client.post(
        "/calculations", json={"a": 9, "b": 3, "type": "Sub", "user_id": user_id}
    )
    assert created.status_code == 201
    calc_id = created.json()["id"]
    row = calculation_row(db_session, calc_id)
    assert (row["type"], row["a"], row["b"], row["result"]) == ("Sub", 9, 3, 6)
    assert str(row["user_id"]) == user_id

    # Retrieve: the API answers with what is in the table
    read = client.get(f"/calculations/{calc_id}").json()
    assert (read["type"], read["a"], read["b"], read["result"]) == ("Sub", 9, 3, 6)

    # Update: new numbers and a recomputed result are saved
    updated = client.patch(f"/calculations/{calc_id}", json={"b": 10})
    assert updated.status_code == 200
    row = calculation_row(db_session, calc_id)
    assert (row["type"], row["a"], row["b"], row["result"]) == ("Sub", 9, 10, -1)

    # Delete: the row is gone, the user stays
    assert client.delete(f"/calculations/{calc_id}").status_code == 204
    assert calculation_row(db_session, calc_id) is None
    assert user_row(db_session, USER["username"]) is not None


@pytest.mark.parametrize(
    ("calculation_type", "a", "b", "expected"),
    [("Add", 2, 3, 5), ("Sub", 2, 3, -1), ("Multiply", 2, 3, 6), ("Divide", 3, 2, 1.5)],
)
def test_each_type_is_stored_with_its_result(
    client, db_session, user_id, calculation_type, a, b, expected
):
    response = client.post(
        "/calculations", json={"a": a, "b": b, "type": calculation_type, "user_id": user_id}
    )
    row = calculation_row(db_session, response.json()["id"])
    assert (row["type"], row["result"]) == (calculation_type, expected)


# ----- Invalid data: status code, error body, nothing stored --------------------


@pytest.mark.parametrize(
    ("payload", "loc", "message"),
    [
        ({"b": 2, "type": "Add"}, ["body", "a"], "Field required"),
        ({"a": "abc", "b": 2, "type": "Add"}, ["body", "a"], "valid number"),
        ({"a": 1, "b": None, "type": "Add"}, ["body", "b"], "valid number"),
        ({"a": 1, "b": 2, "type": "Power"}, ["body", "type"], "Input should be"),
        ({"a": 1, "b": 2}, ["body", "type"], "Field required"),
        ({"a": 1, "b": 0, "type": "Divide"}, ["body"], "b must not be zero"),
        ({"a": 1, "b": 2, "type": "Add", "user_id": "123"}, ["body", "user_id"], "UUID"),
    ],
)
def test_invalid_calculation_returns_422_and_stores_nothing(
    client, db_session, user_id, payload, loc, message
):
    body = {"user_id": user_id, **payload}

    response = client.post("/calculations", json=body)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == loc
    assert message in error["msg"]
    assert count(db_session, "calculations") == 0


def test_result_too_large_returns_422_and_stores_nothing(client, db_session, user_id):
    response = client.post(
        "/calculations", json={"a": 1e308, "b": 10, "type": "Multiply", "user_id": user_id}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Result is too large to store"}
    assert count(db_session, "calculations") == 0


def test_unknown_user_returns_404_and_stores_nothing(client, db_session):
    missing = uuid.uuid4()
    response = client.post(
        "/calculations", json={"a": 1, "b": 2, "type": "Add", "user_id": str(missing)}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": f"User {missing} not found"}
    assert count(db_session, "calculations") == 0


@pytest.mark.parametrize(
    ("changes", "status", "detail"),
    [
        ({"b": 0}, 422, "Cannot divide by zero"),
        ({"a": "abc"}, 422, None),
        ({}, 422, None),
        ({"a": 1e308, "b": 1e-308}, 422, "Result is too large to store"),
    ],
)
def test_invalid_update_leaves_row_unchanged(client, db_session, user_id, changes, status, detail):
    calc_id = client.post(
        "/calculations", json={"a": 8, "b": 2, "type": "Divide", "user_id": user_id}
    ).json()["id"]

    response = client.patch(f"/calculations/{calc_id}", json=changes)

    assert response.status_code == status
    if detail is not None:
        assert response.json() == {"detail": detail}
    row = calculation_row(db_session, calc_id)
    assert (row["a"], row["b"], row["result"]) == (8, 2, 4)


@pytest.mark.parametrize(
    ("method", "body"),
    [("get", None), ("patch", {"a": 1}), ("delete", None)],
)
def test_missing_calculation_returns_404_error_body(client, method, body):
    kwargs = {"json": body} if body is not None else {}
    response = client.request(method.upper(), f"/calculations/{uuid.uuid4()}", **kwargs)
    assert response.status_code == 404
    assert response.json() == {"detail": "Calculation not found"}


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_malformed_calculation_id_returns_422(client, method):
    response = client.request(method, "/calculations/not-a-uuid", json={"a": 1})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "calculation_id"]
