import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from seed_data import STUDENTS_SEED, EQUIPMENT_SEED
import bcrypt
import click

def connect_db(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn

def get_ist_timestamp():
    try:
        kolkata = ZoneInfo("Asia/Kolkata")
    except Exception:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)
    return datetime.now(kolkata)

def init_schema(app):
    """Init schema."""
    conn = connect_db(app)
    conn.execute("CREATE TABLE IF NOT EXISTS admins (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone TEXT, department TEXT, year INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS equipment (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, total_quantity INTEGER NOT NULL CHECK(total_quantity >= 0), available_quantity INTEGER NOT NULL CHECK(available_quantity >= 0), category TEXT, is_active BOOLEAN DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS issue_transactions (issue_id TEXT PRIMARY KEY, student_id TEXT NOT NULL, admin_id TEXT NOT NULL, issue_datetime TEXT NOT NULL, expected_return_datetime TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('issued','overdue','returned','lost')), FOREIGN KEY(student_id) REFERENCES students(id), FOREIGN KEY(admin_id) REFERENCES admins(id))")
    conn.execute("CREATE TABLE IF NOT EXISTS issue_items (id TEXT PRIMARY KEY, issue_id TEXT NOT NULL, equipment_id INTEGER NOT NULL, quantity INTEGER NOT NULL CHECK(quantity > 0), FOREIGN KEY(issue_id) REFERENCES issue_transactions(issue_id), FOREIGN KEY(equipment_id) REFERENCES equipment(id))")
    conn.execute("CREATE TABLE IF NOT EXISTS return_transactions (issue_id TEXT PRIMARY KEY, admin_id TEXT NOT NULL, return_datetime TEXT NOT NULL, equipment_condition TEXT CHECK(equipment_condition IN ('good','damaged','lost')), loss_or_damage_report TEXT, FOREIGN KEY(issue_id) REFERENCES issue_transactions(issue_id), FOREIGN KEY(admin_id) REFERENCES admins(id))")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issue_student ON issue_transactions(student_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issue_status ON issue_transactions(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_equipment_category ON equipment(category)")
    conn.commit()
    conn.close()

def seed_database(app):
    """Seed data."""
    conn = connect_db(app)
    
    # Seed admins
    admin1_exists = conn.execute("SELECT 1 FROM admins WHERE id='admin1'").fetchone()
    if not admin1_exists:
        admin1_pw = bcrypt.hashpw('password'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn.execute("INSERT INTO admins (id, username, password) VALUES ('admin1', 'admin', ?)", (admin1_pw,))
        
    admin2_exists = conn.execute("SELECT 1 FROM admins WHERE id='admin2'").fetchone()
    if not admin2_exists:
        admin2_pw = bcrypt.hashpw('leo'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn.execute("INSERT INTO admins (id, username, password) VALUES ('admin2', 'pranith', ?)", (admin2_pw,))

    # Seed students
    for s in STUDENTS_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO students (id, name, email, phone, department, year) VALUES (?, ?, ?, ?, ?, ?)",
            s
        )

    # Seed equipment
    count = conn.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
    if count == 0:
        for eq in EQUIPMENT_SEED:
            name, total_qty, category = eq
            conn.execute(
                "INSERT INTO equipment (name, total_quantity, available_quantity, category) VALUES (?, ?, ?, ?)",
                (name, total_qty, total_qty, category)
            )

    conn.commit()
    conn.close()

def init_app(app):
    """Init CLI."""
    # Ensure schema
    init_schema(app)
    
    @app.cli.command('seed-db')
    def seed_db_command():
        """Seed DB."""
        init_schema(app)
        seed_database(app)
        click.echo('Initialized schema and seeded database successfully.')
