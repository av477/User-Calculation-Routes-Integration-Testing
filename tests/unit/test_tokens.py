"""Unit tests for JWT access tokens (no database needed)."""

import uuid
from datetime import timedelta

import jwt
import pytest

from app.auth.tokens import InvalidTokenError, create_access_token, decode_access_token
from app.config import get_settings

pytestmark = pytest.mark.unit


def test_round_trip_returns_same_user_id():
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id)) == user_id


def test_token_contains_subject_and_expiry():
    user_id = uuid.uuid4()
    settings = get_settings()
    payload = jwt.decode(
        create_access_token(user_id), settings.jwt_secret_key, algorithms=["HS256"]
    )
    assert payload["sub"] == str(user_id)
    assert payload["exp"] - payload["iat"] == settings.access_token_expire_minutes * 60


def test_expired_token_is_rejected():
    token = create_access_token(uuid.uuid4(), expires_delta=timedelta(seconds=-1))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_token_signed_with_other_key_is_rejected():
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 9999999999},
        "some-other-secret-key-that-is-long-enough",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_unsigned_none_algorithm_token_is_rejected():
    token = jwt.encode({"sub": str(uuid.uuid4()), "exp": 9999999999}, None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


@pytest.mark.parametrize(
    "payload",
    [{"exp": 9999999999}, {"sub": "not-a-uuid", "exp": 9999999999}, {"sub": str(uuid.uuid4())}],
)
def test_token_with_bad_or_missing_claims_is_rejected(payload):
    token = jwt.encode(payload, get_settings().jwt_secret_key, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_garbage_is_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.token")
