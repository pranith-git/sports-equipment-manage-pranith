import os
from urllib.parse import quote

import requests


AUTH_SERVICE_URL = os.environ.get(
    "AUTH_SERVICE_URL", "http://127.0.0.1:5001"
).rstrip("/")
INVENTORY_SERVICE_URL = os.environ.get(
    "INVENTORY_SERVICE_URL", "http://127.0.0.1:5002"
).rstrip("/")
REQUEST_TIMEOUT = float(os.environ.get("SERVICE_REQUEST_TIMEOUT", "5"))


class APIError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _request(method, url, *, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.request(
            method, url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs
        )
    except requests.RequestException as error:
        raise APIError(
            f"Could not reach a backend service: {error}", status_code=503
        ) from error

    if response.status_code >= 400:
        try:
            message = response.json().get("error", "Backend service request failed.")
        except (ValueError, AttributeError):
            message = "Backend service request failed."
        raise APIError(message, response.status_code)

    if response.status_code == 204 or not response.content:
        return None

    try:
        return response.json()
    except ValueError as error:
        raise APIError("Backend service returned an invalid response.") from error


def authenticate(username, password):
    return _request(
        "POST",
        f"{AUTH_SERVICE_URL}/api/auth/login",
        json={"username": username, "password": password},
    )


def logout(token):
    return _request("POST", f"{AUTH_SERVICE_URL}/api/auth/logout", token=token)


def inventory_request(method, path, *, token=None, params=None, payload=None):
    kwargs = {}
    if params is not None:
        kwargs["params"] = params
    if payload is not None:
        kwargs["json"] = payload
    return _request(
        method,
        f"{INVENTORY_SERVICE_URL}{path}",
        token=token,
        **kwargs,
    )


def student_path(student_id):
    return f"/api/students/{quote(student_id, safe='')}"


def issue_path(issue_id):
    return f"/api/issues/{quote(issue_id, safe='')}"
