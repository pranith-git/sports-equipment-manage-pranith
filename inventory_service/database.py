import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from inventory_service.config import DATABASE_PATH, LEGACY_DATABASE_PATH
from seed_data import EQUIPMENT_SEED, STUDENTS_SEED


class ServiceError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@contextmanager
def connect_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        connection.close()


def _copy_legacy_table(source, target, table, columns):
    existing_tables = {
        row["name"]
        for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if table not in existing_tables:
        return

    source_columns = {
        row["name"] for row in source.execute(f'PRAGMA table_info("{table}")')
    }
    selected_columns = [column for column in columns if column in source_columns]
    if not selected_columns:
        return

    column_sql = ", ".join(f'"{column}"' for column in selected_columns)
    placeholders = ", ".join("?" for _ in selected_columns)
    rows = source.execute(f'SELECT {column_sql} FROM "{table}"').fetchall()
    if table == "issue_items":
        rows = [
            row
            for row in rows
            if target.execute(
                "SELECT 1 FROM equipment WHERE id = ?", (row["equipment_id"],)
            ).fetchone()
            and target.execute(
                "SELECT 1 FROM issue_transactions WHERE issue_id = ?",
                (row["issue_id"],),
            ).fetchone()
        ]
    target.executemany(
        f'INSERT OR IGNORE INTO "{table}" ({column_sql}) VALUES ({placeholders})',
        [tuple(row[column] for column in selected_columns) for row in rows],
    )


def _import_legacy_data(connection):
    imported = connection.execute(
        "SELECT 1 FROM service_metadata WHERE key = 'legacy_import_complete'"
    ).fetchone()
    if imported:
        return

    if (
        not LEGACY_DATABASE_PATH.is_file()
        or LEGACY_DATABASE_PATH == Path(DATABASE_PATH)
    ):
        return

    source = sqlite3.connect(LEGACY_DATABASE_PATH)
    source.row_factory = sqlite3.Row
    try:
        _copy_legacy_table(
            source,
            connection,
            "students",
            ("id", "name", "email", "phone", "department", "year"),
        )
        _copy_legacy_table(
            source,
            connection,
            "equipment",
            (
                "id",
                "name",
                "total_quantity",
                "available_quantity",
                "category",
                "is_active",
            ),
        )
        _copy_legacy_table(
            source,
            connection,
            "issue_transactions",
            (
                "issue_id",
                "student_id",
                "admin_id",
                "issue_datetime",
                "expected_return_datetime",
                "status",
            ),
        )
        _copy_legacy_table(
            source,
            connection,
            "issue_items",
            ("id", "issue_id", "equipment_id", "quantity"),
        )
        _copy_legacy_table(
            source,
            connection,
            "return_transactions",
            (
                "issue_id",
                "admin_id",
                "return_datetime",
                "equipment_condition",
                "loss_or_damage_report",
            ),
        )
    finally:
        source.close()

    connection.execute(
        "INSERT INTO service_metadata (key, value) VALUES ('legacy_import_complete', '1')"
    )


def initialize_database():
    with connect_db() as connection:
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS service_metadata (
                       key TEXT PRIMARY KEY,
                       value TEXT NOT NULL
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS students (
                       id TEXT PRIMARY KEY,
                       name TEXT NOT NULL,
                       email TEXT,
                       phone TEXT,
                       department TEXT,
                       year INTEGER
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS equipment (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       name TEXT NOT NULL,
                       total_quantity INTEGER NOT NULL CHECK(total_quantity >= 0),
                       available_quantity INTEGER NOT NULL CHECK(available_quantity >= 0),
                       category TEXT,
                       is_active BOOLEAN NOT NULL DEFAULT 1
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS issue_transactions (
                       issue_id TEXT PRIMARY KEY,
                       student_id TEXT NOT NULL,
                       admin_id TEXT NOT NULL,
                       issue_datetime TEXT NOT NULL,
                       expected_return_datetime TEXT NOT NULL,
                       status TEXT NOT NULL CHECK(status IN ('issued','overdue','returned','lost')),
                       FOREIGN KEY(student_id) REFERENCES students(id)
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS issue_items (
                       id TEXT PRIMARY KEY,
                       issue_id TEXT NOT NULL,
                       equipment_id INTEGER NOT NULL,
                       quantity INTEGER NOT NULL CHECK(quantity > 0),
                       FOREIGN KEY(issue_id) REFERENCES issue_transactions(issue_id),
                       FOREIGN KEY(equipment_id) REFERENCES equipment(id)
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS return_transactions (
                       issue_id TEXT PRIMARY KEY,
                       admin_id TEXT NOT NULL,
                       return_datetime TEXT NOT NULL,
                       equipment_condition TEXT CHECK(equipment_condition IN ('good','damaged','lost')),
                       loss_or_damage_report TEXT,
                       FOREIGN KEY(issue_id) REFERENCES issue_transactions(issue_id)
                   )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_issue_student ON issue_transactions(student_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_issue_status ON issue_transactions(status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_equipment_category ON equipment(category)"
            )
            _import_legacy_data(connection)

            if connection.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
                connection.executemany(
                    """INSERT OR IGNORE INTO students
                       (id, name, email, phone, department, year)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    STUDENTS_SEED,
                )
            if connection.execute("SELECT COUNT(*) FROM equipment").fetchone()[0] == 0:
                connection.executemany(
                    """INSERT INTO equipment
                       (name, total_quantity, available_quantity, category)
                       VALUES (?, ?, ?, ?)""",
                    [
                        (name, quantity, quantity, category)
                        for name, quantity, category in EQUIPMENT_SEED
                    ],
                )


def _ist_now():
    return datetime.now(ZoneInfo("Asia/Kolkata"))


def list_equipment():
    with connect_db() as connection:
        return [
            dict(row)
            for row in connection.execute(
                """SELECT id, name, total_quantity, available_quantity, category
                   FROM equipment WHERE is_active = 1 ORDER BY category, name"""
            ).fetchall()
        ]


def get_dashboard_stats():
    with connect_db() as connection:
        row = connection.execute(
            """SELECT COUNT(*) AS total_types,
                      COALESCE(SUM(total_quantity), 0) AS total_items,
                      COALESCE(SUM(available_quantity), 0) AS available_items
               FROM equipment WHERE is_active = 1"""
        ).fetchone()
    stats = dict(row)
    stats["issued_items"] = stats["total_items"] - stats["available_items"]
    return stats


def add_equipment(name, quantity, category):
    with connect_db() as connection:
        with connection:
            existing = connection.execute(
                """SELECT id, name, total_quantity, available_quantity
                   FROM equipment
                   WHERE LOWER(name) = LOWER(?) AND is_active = 1""",
                (name,),
            ).fetchone()
            if existing:
                total = existing["total_quantity"] + quantity
                available = existing["available_quantity"] + quantity
                connection.execute(
                    """UPDATE equipment
                       SET total_quantity = ?, available_quantity = ?
                       WHERE id = ?""",
                    (total, available, existing["id"]),
                )
                return {
                    "id": existing["id"],
                    "name": existing["name"],
                    "total_quantity": total,
                    "available_quantity": available,
                    "created": False,
                }

            cursor = connection.execute(
                """INSERT INTO equipment
                   (name, total_quantity, available_quantity, category)
                   VALUES (?, ?, ?, ?)""",
                (name, quantity, quantity, category or None),
            )
            return {
                "id": cursor.lastrowid,
                "name": name,
                "total_quantity": quantity,
                "available_quantity": quantity,
                "created": True,
            }


def update_equipment(equipment_id, total_quantity):
    with connect_db() as connection:
        with connection:
            equipment = connection.execute(
                """SELECT id, name, total_quantity, available_quantity
                   FROM equipment WHERE id = ? AND is_active = 1""",
                (equipment_id,),
            ).fetchone()
            if not equipment:
                raise ServiceError("Equipment not found.", 404)

            issued_quantity = (
                equipment["total_quantity"] - equipment["available_quantity"]
            )
            if total_quantity < issued_quantity:
                raise ServiceError(
                    "Total quantity cannot be less than the currently issued amount "
                    f"({issued_quantity}).",
                    409,
                )

            available_quantity = total_quantity - issued_quantity
            connection.execute(
                """UPDATE equipment
                   SET total_quantity = ?, available_quantity = ? WHERE id = ?""",
                (total_quantity, available_quantity, equipment_id),
            )
    return {
        "id": equipment_id,
        "name": equipment["name"],
        "total_quantity": total_quantity,
        "available_quantity": available_quantity,
    }


def delete_equipment(equipment_id):
    with connect_db() as connection:
        with connection:
            equipment = connection.execute(
                "SELECT id FROM equipment WHERE id = ? AND is_active = 1",
                (equipment_id,),
            ).fetchone()
            if not equipment:
                raise ServiceError("Equipment not found.", 404)
            active_issues = connection.execute(
                """SELECT COUNT(*) FROM issue_items AS item
                   JOIN issue_transactions AS issue ON issue.issue_id = item.issue_id
                   WHERE item.equipment_id = ? AND issue.status = 'issued'""",
                (equipment_id,),
            ).fetchone()[0]
            if active_issues:
                raise ServiceError(
                    "Cannot delete equipment while it has active issues.", 409
                )
            connection.execute(
                "UPDATE equipment SET is_active = 0 WHERE id = ?", (equipment_id,)
            )


def get_student(student_id):
    with connect_db() as connection:
        student = connection.execute(
            "SELECT id, name, email, phone, department, year FROM students WHERE id = ?",
            (student_id.upper(),),
        ).fetchone()
    if not student:
        raise ServiceError("Student not found.", 404)
    return dict(student)


def issue_equipment(student_id, equipment_id, quantity, admin_id):
    now = _ist_now()
    issue_id = f"{student_id}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    expected_return = (
        "N/A"
        if student_id in {"24261A05A5", "24261A05B5"}
        else (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    )
    with connect_db() as connection:
        with connection:
            student = connection.execute(
                "SELECT id FROM students WHERE id = ?", (student_id.upper(),)
            ).fetchone()
            if not student:
                raise ServiceError(
                    "Student not found. Please scan a valid student ID barcode.", 404
                )
            equipment = connection.execute(
                """SELECT id, name, available_quantity FROM equipment
                   WHERE id = ? AND is_active = 1""",
                (equipment_id,),
            ).fetchone()
            if not equipment:
                raise ServiceError("Equipment not found.", 404)
            if equipment["available_quantity"] < quantity:
                raise ServiceError("Insufficient equipment quantity available.", 409)

            connection.execute(
                """INSERT INTO issue_transactions
                   (issue_id, student_id, admin_id, issue_datetime,
                    expected_return_datetime, status)
                   VALUES (?, ?, ?, ?, ?, 'issued')""",
                (
                    issue_id,
                    student_id.upper(),
                    admin_id,
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                    expected_return,
                ),
            )
            connection.execute(
                """INSERT INTO issue_items (id, issue_id, equipment_id, quantity)
                   VALUES (?, ?, ?, ?)""",
                (f"{issue_id}_item", issue_id, equipment_id, quantity),
            )
            connection.execute(
                """UPDATE equipment
                   SET available_quantity = available_quantity - ? WHERE id = ?""",
                (quantity, equipment_id),
            )
    return {
        "issue_id": issue_id,
        "student_id": student_id.upper(),
        "equipment_id": equipment_id,
        "equipment_name": equipment["name"],
        "quantity": quantity,
        "issue_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "expected_return_datetime": expected_return,
        "status": "issued",
    }


def list_issues(status, student_id=None):
    conditions = []
    parameters = []
    if status and status != "all":
        conditions.append("issue.status = ?")
        parameters.append(status)
    if student_id:
        conditions.append("issue.student_id = ?")
        parameters.append(student_id.upper())
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with connect_db() as connection:
        rows = connection.execute(
            f"""SELECT issue.issue_id, issue.student_id, student.name AS student_name,
                       item.equipment_id, equipment.name AS equipment_name, item.quantity,
                       issue.issue_datetime, issue.expected_return_datetime, issue.status
                FROM issue_transactions AS issue
                JOIN issue_items AS item ON item.issue_id = issue.issue_id
                JOIN equipment ON equipment.id = item.equipment_id
                JOIN students AS student ON student.id = issue.student_id
                {where_clause}
                ORDER BY issue.issue_datetime DESC""",
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def return_issue(issue_id, condition, damage_report, admin_id):
    if condition not in {"good", "damaged", "lost"}:
        raise ServiceError("Condition must be good, damaged, or lost.")
    returned_at = _ist_now().strftime("%Y-%m-%d %H:%M:%S")
    with connect_db() as connection:
        with connection:
            issue = connection.execute(
                "SELECT status FROM issue_transactions WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            if not issue or issue["status"] != "issued":
                raise ServiceError(
                    "Issue record not found or already returned.", 404
                )
            items = connection.execute(
                "SELECT equipment_id, quantity FROM issue_items WHERE issue_id = ?",
                (issue_id,),
            ).fetchall()

            for item in items:
                if condition == "lost":
                    connection.execute(
                        """UPDATE equipment
                           SET total_quantity = total_quantity - ? WHERE id = ?""",
                        (item["quantity"], item["equipment_id"]),
                    )
                else:
                    connection.execute(
                        """UPDATE equipment
                           SET available_quantity = available_quantity + ? WHERE id = ?""",
                        (item["quantity"], item["equipment_id"]),
                    )

            new_status = "lost" if condition == "lost" else "returned"
            connection.execute(
                "UPDATE issue_transactions SET status = ? WHERE issue_id = ?",
                (new_status, issue_id),
            )
            connection.execute(
                """INSERT INTO return_transactions
                   (issue_id, admin_id, return_datetime, equipment_condition,
                    loss_or_damage_report)
                   VALUES (?, ?, ?, ?, ?)""",
                (issue_id, admin_id, returned_at, condition, damage_report or None),
            )
    return {
        "issue_id": issue_id,
        "status": new_status,
        "equipment_condition": condition,
        "return_datetime": returned_at,
    }


def get_reports(page, per_page, student_filter="", status_filter=""):
    conditions = []
    parameters = []
    if student_filter:
        conditions.append("issue.student_id LIKE ?")
        parameters.append(f"%{student_filter}%")
    if status_filter and status_filter != "all":
        conditions.append("issue.status = ?")
        parameters.append(status_filter)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with connect_db() as connection:
        total_records = connection.execute(
            f"""SELECT COUNT(*)
                FROM issue_transactions AS issue
                JOIN issue_items AS item ON issue.issue_id = item.issue_id
                JOIN equipment ON item.equipment_id = equipment.id
                JOIN students AS student ON issue.student_id = student.id
                LEFT JOIN return_transactions AS returned
                    ON issue.issue_id = returned.issue_id
                {where_clause}""",
            parameters,
        ).fetchone()[0]
        total_pages = max(1, (total_records + per_page - 1) // per_page)
        page = min(page, total_pages)
        rows = connection.execute(
            f"""SELECT issue.issue_id, issue.student_id, student.name AS student_name,
                       equipment.name AS equipment_name, item.quantity,
                       issue.issue_datetime, issue.expected_return_datetime, issue.status,
                       returned.equipment_condition, returned.loss_or_damage_report,
                       returned.return_datetime, issue.admin_id
                FROM issue_transactions AS issue
                JOIN issue_items AS item ON issue.issue_id = item.issue_id
                JOIN equipment ON item.equipment_id = equipment.id
                JOIN students AS student ON issue.student_id = student.id
                LEFT JOIN return_transactions AS returned
                    ON issue.issue_id = returned.issue_id
                {where_clause}
                ORDER BY issue.issue_datetime DESC
                LIMIT ? OFFSET ?""",
            parameters + [per_page, (page - 1) * per_page],
        ).fetchall()
    return {
        "reports": [dict(row) for row in rows],
        "page": page,
        "total_pages": total_pages,
        "total_records": total_records,
    }
