import os
import secrets
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect

from frontend.api_client import (
    APIError,
    authenticate,
    inventory_request,
    issue_path,
    logout,
    student_path,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower()
    in {"1", "true", "yes"},
)
csrf = CSRFProtect(app)


def login_required(view):
    @wraps(view)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_id") or not session.get("access_token"):
            flash("Please log in to the page", "warning")
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)

    return decorated_function


def _show_api_error(error):
    flash(error.message, "danger")


def _action_error_redirect(error, endpoint):
    if error.status_code >= 500:
        raise error
    if error.status_code == 401:
        session.clear()
        flash("Your session has expired. Please log in again.", "warning")
        return redirect(url_for("login_page"))
    _show_api_error(error)
    return redirect(url_for(endpoint))


@app.errorhandler(APIError)
def handle_api_error(error):
    return render_template("service_error.html", message=error.message), error.status_code


@app.route("/")
def home():
    equipment = inventory_request("GET", "/api/equipment")
    stats = inventory_request("GET", "/api/dashboard")
    return render_template("home.html", items=equipment, stats=stats)


@app.route("/login.html")
@app.route("/login_page")
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or not password:
        flash("Please enter both username and password.", "danger")
        return redirect(url_for("login_page"))

    try:
        result = authenticate(username, password)
    except APIError as error:
        if error.status_code == 401:
            flash("Invalid credentials", "danger")
            return redirect(url_for("login_page"))
        return handle_api_error(error)

    session.clear()
    session.permanent = True
    session["admin_id"] = result["admin_id"]
    session["username"] = result["username"]
    session["access_token"] = result["access_token"]
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout_page():
    token = session.get("access_token")
    session.clear()
    if token:
        try:
            logout(token)
        except APIError as error:
            app.logger.warning("Authentication service logout request failed: %s", error)
    flash("You have been logged out.", "info")
    return redirect(url_for("login_page"))


@app.route("/dashboard")
@login_required
def dashboard():
    stats = inventory_request(
        "GET", "/api/dashboard", token=session["access_token"]
    )
    return render_template("dashboard.html", stats=stats)


@app.route("/equipment")
@login_required
def equipment():
    items = inventory_request(
        "GET", "/api/equipment", token=session["access_token"]
    )
    return render_template("equipment.html", items=items)


@app.route("/add_equipment", methods=["POST"])
@login_required
def add_equipment():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    try:
        quantity = int(request.form.get("qty", "0"))
        inventory_request(
            "POST",
            "/api/equipment",
            token=session["access_token"],
            payload={"name": name, "quantity": quantity, "category": category},
        )
        flash("Equipment added or existing stock updated successfully.", "success")
    except ValueError:
        flash("Quantity must be a whole number.", "danger")
    except APIError as error:
        return _action_error_redirect(error, "equipment")
    return redirect(url_for("equipment"))


@app.route("/delete_equipment/<int:eq_id>", methods=["POST"])
@login_required
def delete_equipment(eq_id):
    try:
        inventory_request(
            "DELETE", f"/api/equipment/{eq_id}", token=session["access_token"]
        )
        flash("Equipment deleted.", "success")
    except APIError as error:
        return _action_error_redirect(error, "equipment")
    return redirect(url_for("equipment"))


@app.route("/update_equipment_qty/<int:eq_id>", methods=["POST"])
@login_required
def update_equipment_qty(eq_id):
    total = request.form.get("new_total", type=int)
    try:
        inventory_request(
            "PUT",
            f"/api/equipment/{eq_id}",
            token=session["access_token"],
            payload={"total_quantity": total},
        )
        flash("Equipment stock updated.", "success")
    except APIError as error:
        return _action_error_redirect(error, "equipment")
    return redirect(url_for("equipment"))


@app.route("/issue", methods=["GET", "POST"])
@login_required
def issue():
    token = session["access_token"]
    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantity", "1"))
        except ValueError:
            flash("Quantity must be a whole number.", "danger")
            return redirect(url_for("issue"))

        payload = {
            "student_id": request.form.get("student_id", "").strip().upper(),
            "equipment_id": request.form.get("equipment_id", ""),
            "quantity": quantity,
        }
        try:
            inventory_request(
                "POST", "/api/issues", token=token, payload=payload
            )
            flash("Equipment issued successfully.", "success")
            return redirect(url_for("reports"))
        except APIError as error:
            return _action_error_redirect(error, "issue")

    items = inventory_request("GET", "/api/equipment", token=token)
    student_id = request.args.get("student_id", "").strip().upper()
    student = None
    if student_id:
        try:
            student = inventory_request(
                "GET", student_path(student_id), token=token
            )
            if student_id in {"24261A05A5", "24261A05B5"}:
                flash(f"Welcome Creator, {student['name']}!", "info")
        except APIError as error:
            if error.status_code == 404:
                flash(f'Student ID "{student_id}" not found in the database.', "danger")
            else:
                raise

    return render_template(
        "issue.html",
        equipment=items,
        student=student,
        selected_equipment=request.args.get("equipment_id", ""),
    )


@app.route("/return", methods=["GET", "POST"])
@login_required
def return_equipment():
    token = session["access_token"]
    if request.method == "POST":
        issue_id = request.form.get("issue_id", "")
        try:
            inventory_request(
                "POST",
                f"{issue_path(issue_id)}/return",
                token=token,
                payload={
                    "condition": request.form.get("condition", "good"),
                    "damage_report": request.form.get("damage_report", "").strip(),
                },
            )
        except APIError as error:
            return _action_error_redirect(error, "return_equipment")

        condition = request.form.get("condition", "good")
        if condition == "lost":
            flash("Record closed as LOST. Equipment stock was adjusted.", "warning")
        elif condition == "damaged":
            flash("Returned and marked as DAMAGED.", "warning")
        else:
            flash("Returned successfully.", "success")
        return redirect(url_for("dashboard"))

    student_id = request.args.get("student_id", "").strip().upper()
    student = None
    params = {"status": "issued"}
    if student_id:
        params["student_id"] = student_id
        try:
            student = inventory_request(
                "GET", student_path(student_id), token=token
            )
        except APIError as error:
            if error.status_code == 404:
                flash(f'Student ID "{student_id}" not found.', "danger")
            else:
                raise
    issues = inventory_request(
        "GET", "/api/issues", token=token, params=params
    )
    return render_template("return.html", issues=issues, student=student)


@app.route("/reports")
@login_required
def reports():
    params = {
        "page": request.args.get("page", 1, type=int),
        "student_id": request.args.get("student_id", "").strip(),
        "status": request.args.get("status", "").strip(),
    }
    result = inventory_request(
        "GET", "/api/reports", token=session["access_token"], params=params
    )
    return render_template(
        "reports.html",
        reports=result["reports"],
        page=result["page"],
        total_pages=result["total_pages"],
        student_filter=params["student_id"],
        status_filter=params["status"],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
