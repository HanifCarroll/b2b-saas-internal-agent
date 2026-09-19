import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from switchboard import auth

TENANT = "b1338704-8cc0-43f7-846c-d930c917b905"
API = "78e83c6d-0b97-47ee-aa39-114da2139341"
WEB = "28093c48-1122-403b-b63f-99717ddf5e4c"
USER = "9b1cc57a-04b9-45a1-95e9-f7ffa9535a61"


@pytest.fixture
def identity(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_API_CLIENT_ID", API)
    monkeypatch.setenv("ENTRA_WEB_CLIENT_ID", WEB)
    monkeypatch.setenv("ENTRA_EMPLOYEE_MAPPING", '{"' + USER + '": "emp-alex"}')
    auth.get_entra_settings.cache_clear()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        auth,
        "get_signing_key_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(
                key=private_key.public_key()
            )
        ),
    )
    now = int(time.time())
    claims = {
        "aud": API,
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "tid": TENANT,
        "oid": USER,
        "azp": WEB,
        "ver": "2.0",
        "scp": "access_as_user",
        "iat": now,
        "nbf": now - 1,
        "exp": now + 300,
    }
    yield private_key, claims
    auth.get_entra_settings.cache_clear()


def test_verified_token_maps_to_business_employee(identity):
    key, claims = identity
    token = jwt.encode(claims, key, algorithm="RS256")

    assert auth.authenticate_access_token(token) == "emp-alex"


def test_token_without_delegated_scope_is_rejected(identity):
    key, claims = identity
    claims["scp"] = "User.Read"
    token = jwt.encode(claims, key, algorithm="RS256")

    with pytest.raises(HTTPException) as error:
        auth.authenticate_access_token(token)
    assert error.value.status_code == 403
