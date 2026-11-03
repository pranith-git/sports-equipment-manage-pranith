import uuid
from datetime import datetime, timezone
from functools import wraps

import bcrypt
from flask import Blueprint, current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from auth_service.config import TOKEN_MAX_AGE, TOKEN_SECRET
from auth_service.database import (
    find_admin,
    revoke_token,
    token_is_revoked,
)


auth_api = Blueprint("auth_api", __name__, url_prefix="/api/auth")
TOKEN_SALT = "sports-equipment-access"


def _serializer():
    return URLSafeTimedSerializer(TOKEN_SECRET, salt=TOKEN_SALT)


def _read_token():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        return None

    try:
        claims = _serializer().loads(token.strip(), max_age=TOKEN_MAX_AGE)
    except SignatureExpired:
        return None
    except BadSignature:
        return None

    if not isinstance(claims, dict) or not claims.get("admin_id") or not claims.get("jti"):
        return None
    if token_is_revoked(claims["jti"]):
        return None
    return claims


def require_token(view):
    @wraps(view)
    def decorated(*args, **kwargs):
        claims = _read_token()
        if claims is None:
            return jsonify(error="A valid access token is required."), 401
        g.auth_claims = claims
        return view(*args, **kwargs)

    return decorated


@auth_api.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="Username and password are required."), 400

    admin = find_admin(username.strip())
    valid_password = False
    if admin:
        try:
            valid_password = bcrypt.checkpw(
                password.encode("utf-8"), admin["password_hash"].encode("utf-8")
            )
        except (ValueError, TypeError):
            current_app.logger.warning(
                "Stored password hash for admin %s is invalid.", admin["id"]
            )
    if not admin or not valid_password:
        return jsonify(error="Invalid username or password."), 401

    access_token = _serializer().dumps(
        {
            "admin_id": admin["id"],
            "username": admin["username"],
            "jti": uuid.uuid4().hex,
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return jsonify(
        access_token=access_token,
        admin_id=admin["id"],
        username=admin["username"],
        token_type="Bearer",
        expires_in=TOKEN_MAX_AGE,
    )


@auth_api.get("/verify")
@require_token
def verify():
    claims = g.auth_claims
    return jsonify(
        valid=True,
        admin_id=claims["admin_id"],
        username=claims["username"],
    )


@auth_api.post("/logout")
@require_token
def logout():
    revoke_token(g.auth_claims["jti"])
    return "", 204
