from functools import wraps

import requests
from flask import Blueprint, current_app, g, jsonify, request

from inventory_service.config import AUTH_SERVICE_URL, SERVICE_REQUEST_TIMEOUT
from inventory_service.database import (
    ServiceError,
    add_equipment,
    delete_equipment,
    get_dashboard_stats,
    get_reports,
    get_student,
    issue_equipment,
    list_equipment,
    list_issues,
    return_issue,
    update_equipment,
)


inventory_api = Blueprint("inventory_api", __name__, url_prefix="/api")


def _json_object():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ServiceError("A JSON object is required.")
    return payload


def require_admin(view):
    @wraps(view)
    def decorated(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        try:
            response = requests.get(
                f"{AUTH_SERVICE_URL}/api/auth/verify",
                headers={"Authorization": authorization},
                timeout=SERVICE_REQUEST_TIMEOUT,
            )
        except requests.RequestException as error:
            current_app.logger.error("Authentication service request failed: %s", error)
            return jsonify(error="Authentication service is unavailable."), 503

        if response.status_code == 401:
            return jsonify(error="A valid access token is required."), 401
        if not response.ok:
            current_app.logger.error(
                "Authentication service verification returned HTTP %s.",
                response.status_code,
            )
            return jsonify(error="Authentication service is unavailable."), 503
        try:
            identity = response.json()
        except ValueError:
            current_app.logger.error("Authentication service returned invalid JSON.")
            return jsonify(error="Authentication service returned an invalid response."), 503
        if (
            not isinstance(identity, dict)
            or not identity.get("valid")
            or not identity.get("admin_id")
        ):
            return jsonify(error="A valid access token is required."), 401

        g.admin_id = identity["admin_id"]
        return view(*args, **kwargs)

    return decorated


@inventory_api.get("/health")
def health():
    return jsonify(service="inventory", status="ok")


@inventory_api.get("/dashboard")
def dashboard():
    return jsonify(get_dashboard_stats())


@inventory_api.get("/equipment")
def equipment_list():
    return jsonify(list_equipment())


@inventory_api.post("/equipment")
@require_admin
def equipment_create():
    payload = _json_object()
    name = payload.get("name")
    quantity = payload.get("quantity")
    category = payload.get("category", "")
    if not isinstance(name, str) or not name.strip():
        raise ServiceError("Equipment name is required.")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ServiceError("Quantity must be a positive whole number.")
    if not isinstance(category, str):
        raise ServiceError("Category must be text.")

    result = add_equipment(name.strip(), quantity, category.strip())
    return jsonify(result), 201 if result["created"] else 200


@inventory_api.put("/equipment/<int:equipment_id>")
@require_admin
def equipment_update(equipment_id):
    payload = _json_object()
    total_quantity = payload.get("total_quantity")
    if (
        isinstance(total_quantity, bool)
        or not isinstance(total_quantity, int)
        or total_quantity < 0
    ):
        raise ServiceError("Total quantity must be a non-negative whole number.")
    return jsonify(update_equipment(equipment_id, total_quantity))


@inventory_api.delete("/equipment/<int:equipment_id>")
@require_admin
def equipment_delete(equipment_id):
    delete_equipment(equipment_id)
    return "", 204


@inventory_api.get("/students/<student_id>")
@require_admin
def student_detail(student_id):
    return jsonify(get_student(student_id))


@inventory_api.post("/issues")
@require_admin
def issue_create():
    payload = _json_object()
    student_id = payload.get("student_id")
    equipment_id = payload.get("equipment_id")
    quantity = payload.get("quantity")
    if not isinstance(student_id, str) or not student_id.strip():
        raise ServiceError("Student ID is required.")
    try:
        equipment_id = int(equipment_id)
    except (TypeError, ValueError):
        raise ServiceError("A valid equipment ID is required.")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ServiceError("Quantity must be a positive whole number.")

    result = issue_equipment(
        student_id.strip().upper(), equipment_id, quantity, g.admin_id
    )
    return jsonify(result), 201


@inventory_api.get("/issues")
@require_admin
def issues_list():
    status = request.args.get("status", "issued").strip()
    valid_statuses = {"all", "issued", "overdue", "returned", "lost"}
    if status not in valid_statuses:
        raise ServiceError("Unsupported issue status.")
    student_id = request.args.get("student_id", "").strip()
    return jsonify(list_issues(status, student_id or None))


@inventory_api.post("/issues/<path:issue_id>/return")
@require_admin
def issue_return(issue_id):
    payload = _json_object()
    condition = payload.get("condition", "good")
    damage_report = payload.get("damage_report", "")
    if not isinstance(condition, str):
        raise ServiceError("Condition must be text.")
    if not isinstance(damage_report, str):
        raise ServiceError("Damage report must be text.")

    result = return_issue(
        issue_id, condition.strip().lower(), damage_report.strip(), g.admin_id
    )
    return jsonify(result)


@inventory_api.get("/reports")
@require_admin
def reports_list():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        raise ServiceError("Page and per_page must be whole numbers.")
    if page < 1 or per_page < 1 or per_page > 100:
        raise ServiceError("Page must be positive and per_page must be between 1 and 100.")

    return jsonify(
        get_reports(
            page,
            per_page,
            request.args.get("student_id", "").strip(),
            request.args.get("status", "").strip(),
        )
    )
