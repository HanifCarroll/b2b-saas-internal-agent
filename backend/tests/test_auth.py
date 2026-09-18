"""Exercise token verification with real local signatures; no Microsoft calls."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from test_api import review_api  # noqa: F401

from switchboard import api, auth

TENANT = "b1338704-8cc0-43f7-846c-d930c917b905"
API = "78e83c6d-0b97-47ee-aa39-114da2139341"
WEB = "28093c48-1122-403b-b63f-99717ddf5e4c"
USER = "9b1cc57a-04b9-45a1-95e9-f7ffa9535a61"


@pytest.fixture
def identity(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_AUTH_MODE", "entra")
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
            get_signing_key_from_jwt=lambda token: SimpleNamespace(
                key=private_key.public_key()
            )
        ),
    )
    claims = {
        "aud": API,
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "tid": TENANT,
        "oid": USER,
        "azp": WEB,
        "ver": "2.0",
        "scp": "access_as_user",
        "iat": int(time.time()),
        "nbf": int(time.time()) - 1,
        "exp": int(time.time()) + 300,
    }
    yield private_key, claims
    auth.get_entra_settings.cache_clear()


def test_verified_identity_reaches_business_routes(identity, monkeypatch, tmp_path):
    key, claims = identity
    token = jwt.encode(claims, key, algorithm="RS256")
    monkeypatch.setattr(api, "DATABASE_PATH", tmp_path / "demo.db")
    seen = []

    def history(*, runs_directory, employee_id):
        seen.append(employee_id)
        return []

    monkeypatch.setattr(api, "list_investigation_runs", history)
    client = TestClient(api.app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/investigations", headers=headers).status_code == 200
    assert seen == ["emp-alex"]
    assert (
        client.get(
            "/api/investigations", headers=headers | {"X-Employee-Id": "emp-priya"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/demo/reset",
            headers=headers,
            json={"scenario_id": "baseline", "confirm": True},
        ).status_code
        == 403
    )
    assert seen == ["emp-alex"]


@pytest.mark.parametrize(
    "claim,value",
    [
        ("aud", WEB),
        ("iss", "https://evil.example"),
        ("exp", 1),
        ("nbf", 9999999999),
        ("tid", WEB),
        ("azp", API),
        ("ver", "1.0"),
        ("scp", "other"),
        ("scp", []),
        ("oid", WEB),
    ],
)
def test_invalid_claims_rejected(identity, claim, value):
    key, claims = identity
    claims[claim] = value
    with pytest.raises(auth.HTTPException) as error:
        auth.authenticate_access_token(jwt.encode(claims, key, algorithm="RS256"))
    assert error.value.status_code in {401, 403}


def test_missing_claim_and_bad_signature_rejected(identity):
    key, claims = identity
    del claims["scp"]
    with pytest.raises(auth.HTTPException, match="Invalid access token"):
        auth.authenticate_access_token(jwt.encode(claims, key, algorithm="RS256"))
    claims["scp"] = "access_as_user"
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(auth.HTTPException, match="Invalid access token"):
        auth.authenticate_access_token(jwt.encode(claims, wrong_key, algorithm="RS256"))
    with pytest.raises(auth.HTTPException, match="Invalid access token"):
        auth.authenticate_access_token(jwt.encode(claims, "x" * 32, algorithm="HS256"))


@pytest.mark.parametrize(
    "path", ["/api/demo", "/api/demo-options", "/api/investigations"]
)
def test_every_read_requires_authentication(identity, path):
    client = TestClient(api.app)
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Employee-Id": "emp-alex"}).status_code == 400


def test_mode_fails_closed(monkeypatch):
    monkeypatch.delenv("SWITCHBOARD_AUTH_MODE", raising=False)
    assert auth.get_auth_mode() == "entra"
    monkeypatch.setenv("SWITCHBOARD_AUTH_MODE", "typo")
    with pytest.raises(RuntimeError):
        auth.get_auth_mode()


def test_provider_outage_is_not_invalid_credentials(identity, monkeypatch):
    def unavailable(token):
        raise jwt.PyJWKClientConnectionError("offline")

    monkeypatch.setattr(
        auth,
        "get_signing_key_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=unavailable),
    )
    with pytest.raises(auth.HTTPException) as error:
        auth.authenticate_access_token("token")
    assert error.value.status_code == 503


def test_entra_identity_still_obeys_business_authorization(identity, review_api):  # noqa: F811
    import sqlite3
    from contextlib import closing

    key, claims = identity
    client, url, _ = review_api
    headers = {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}
    assert client.get(url, headers=headers).status_code == 200
    assert client.post(url + "/approval", headers=headers).status_code == 403

    with closing(sqlite3.connect(api.DATABASE_PATH)) as connection, connection:
        connection.execute("UPDATE employees SET active = 0 WHERE id = 'emp-alex'")

    assert client.get(url, headers=headers).status_code == 404
    assert client.post(url + "/execution", headers=headers).status_code == 403


def test_missing_entra_configuration_prevents_startup(monkeypatch):
    monkeypatch.setenv("SWITCHBOARD_AUTH_MODE", "entra")
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    monkeypatch.setattr(api, "load_dotenv", lambda *args: None)
    auth.get_entra_settings.cache_clear()
    with pytest.raises(KeyError):
        with TestClient(api.app):
            pass
    auth.get_entra_settings.cache_clear()


def test_current_employee_returns_mapped_identity_and_database_role(
    identity,
    review_api,  # noqa: F811
):
    signing_key, claims = identity
    client, _, _ = review_api
    access_token = jwt.encode(claims, signing_key, algorithm="RS256")

    response = client.get(
        "/api/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "employee_id": "emp-alex",
        "role": "implementation_engineer",
    }


@pytest.mark.parametrize(
    "case,expected_status",
    [
        ("inactive", 403),
        ("missing_token", 401),
        ("expired_token", 401),
        ("unmapped_user", 403),
        ("identity_override", 400),
    ],
)
def test_current_employee_rejects_unavailable_identity(
    identity,
    review_api,  # noqa: F811
    case,
    expected_status,
):
    import sqlite3
    from contextlib import closing

    signing_key, claims = identity
    client, _, _ = review_api
    if case == "inactive":
        with closing(sqlite3.connect(api.DATABASE_PATH)) as connection, connection:
            connection.execute("UPDATE employees SET active = 0 WHERE id = 'emp-alex'")
    elif case == "expired_token":
        claims["exp"] = 1
    elif case == "unmapped_user":
        claims["oid"] = WEB

    access_token = jwt.encode(claims, signing_key, algorithm="RS256")
    headers = {"Authorization": f"Bearer {access_token}"}
    if case == "missing_token":
        headers = {}
    elif case == "identity_override":
        headers["X-Employee-Id"] = "emp-priya"

    response = client.get("/api/me", headers=headers)

    assert response.status_code == expected_status
    assert set(response.json()) == {"detail"}


def test_current_employee_reads_updated_role(identity, review_api):  # noqa: F811
    import sqlite3
    from contextlib import closing

    signing_key, claims = identity
    client, _, _ = review_api
    # The token's claimed role must not override the current business directory.
    claims["roles"] = ["technical_lead"]
    access_token = jwt.encode(claims, signing_key, algorithm="RS256")
    headers = {"Authorization": f"Bearer {access_token}"}
    assert (
        client.get("/api/me", headers=headers).json()["role"]
        == "implementation_engineer"
    )

    with closing(sqlite3.connect(api.DATABASE_PATH)) as connection, connection:
        connection.execute(
            "UPDATE employees SET role = 'support_specialist' WHERE id = 'emp-alex'"
        )

    assert client.get("/api/me", headers=headers).json() == {
        "employee_id": "emp-alex",
        "role": "support_specialist",
    }


def test_current_employee_supports_explicit_demo_identity(review_api, monkeypatch):  # noqa: F811
    monkeypatch.setenv("SWITCHBOARD_AUTH_MODE", "demo")
    client, _, _ = review_api

    response = client.get("/api/me", headers={"X-Employee-Id": "emp-priya"})

    assert response.status_code == 200
    assert response.json() == {"employee_id": "emp-priya", "role": "technical_lead"}
