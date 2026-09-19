"""Resolve employee identity from an Entra token or explicit local demo mode."""

import json
import os
from functools import lru_cache
from typing import Literal
from uuid import UUID

import jwt
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field


class EntraSettings(BaseModel):
    tenant_id: UUID
    api_client_id: UUID
    web_client_id: UUID
    employee_id_by_entra_object_id: dict[UUID, str] = Field(min_length=1)


def get_auth_mode() -> Literal["demo", "entra"]:
    mode = os.getenv("SWITCHBOARD_AUTH_MODE", "entra")
    if mode != "demo" and mode != "entra":
        raise RuntimeError("SWITCHBOARD_AUTH_MODE must be demo or entra")
    return mode


@lru_cache
def get_entra_settings() -> EntraSettings:
    return EntraSettings(
        tenant_id=UUID(os.environ["ENTRA_TENANT_ID"]),
        api_client_id=UUID(os.environ["ENTRA_API_CLIENT_ID"]),
        web_client_id=UUID(os.environ["ENTRA_WEB_CLIENT_ID"]),
        employee_id_by_entra_object_id=json.loads(os.environ["ENTRA_EMPLOYEE_MAPPING"]),
    )


@lru_cache
def get_signing_key_client() -> jwt.PyJWKClient:
    tenant_id = get_entra_settings().tenant_id
    return jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
        timeout=5,
    )


def authenticate_access_token(access_token: str) -> str:
    """Validate a v2 delegated API access token and return its mapped employee ID."""
    # 1. Verify the signature, intended API, tenant issuer, and token lifetime.
    settings = get_entra_settings()
    try:
        signing_key = (
            get_signing_key_client().get_signing_key_from_jwt(access_token).key
        )
        claims = jwt.decode(
            access_token,
            signing_key,
            algorithms=["RS256"],
            audience=str(settings.api_client_id),
            issuer=f"https://login.microsoftonline.com/{settings.tenant_id}/v2.0",
            options={
                "require": [
                    "exp",
                    "iat",
                    "nbf",
                    "iss",
                    "aud",
                    "tid",
                    "oid",
                    "scp",
                    "azp",
                    "ver",
                ]
            },
        )
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(
            status_code=503, detail="Identity provider unavailable"
        ) from None
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    # 2. Require our tenant, frontend, and delegated API permission.
    scope_text = claims["scp"]
    if (
        claims["ver"] != "2.0"
        or claims["tid"] != str(settings.tenant_id)
        or claims["azp"] != str(settings.web_client_id)
        or not isinstance(scope_text, str)
        or "access_as_user" not in scope_text.split()
    ):
        raise HTTPException(status_code=403, detail="Token not permitted")

    # 3. Bind only an explicitly mapped identity; roles remain in business records.
    try:
        entra_object_id = UUID(claims["oid"])
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=403, detail="Employee unavailable") from None

    employee_id = settings.employee_id_by_entra_object_id.get(entra_object_id)
    if not employee_id:
        raise HTTPException(status_code=403, detail="Employee unavailable")

    return employee_id


def get_request_employee_id(request: Request) -> str:
    """Return the employee ID from verified Entra identity or explicit demo mode."""
    if get_auth_mode() == "demo":
        employee_id = request.headers.get("X-Demo-Persona-Id")
        if not employee_id:
            raise HTTPException(
                status_code=422, detail="X-Demo-Persona-Id required in demo mode"
            )
        return employee_id

    if hasattr(request.state, "employee_id"):
        return request.state.employee_id

    # Entra mode never accepts a caller-selected persona, even with a valid token.
    if "X-Demo-Persona-Id" in request.headers:
        raise HTTPException(status_code=400, detail="Simulated identity is disabled")

    scheme, _, access_token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not access_token.strip():
        raise HTTPException(
            status_code=401,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return authenticate_access_token(access_token)


def require_api_authentication(request: Request) -> None:
    """Protect every API route in Entra mode, including demo metadata."""
    if get_auth_mode() == "entra":
        request.state.employee_id = get_request_employee_id(request)
