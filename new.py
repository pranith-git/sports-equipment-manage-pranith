import sqlite3

conn = sqlite3.connect("basedata.db")
conn.execute("PRAGMA foreign_keys = ON")

# admins table stores login credentials
conn.execute("""
CREATE TABLE IF NOT EXISTS admins (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)
""")

# insert default admin safely
conn.execute("""
INSERT OR IGNORE INTO admins(id, username, password)
VALUES ('admin1', 'admin', 'password')
""")

# students table (ID is used as barcode)
conn.execute("""
CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    department TEXT,
    year INTEGER
)
""")

# equipment table stores inventory
conn.execute("""
CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    total_quantity INTEGER NOT NULL CHECK(total_quantity >= 0),
    available_quantity INTEGER NOT NULL CHECK(available_quantity >= 0),
    category TEXT
)
""")

# issue_transactions tracks each issue
conn.execute("""
CREATE TABLE IF NOT EXISTS issue_transactions (
    issue_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    admin_id TEXT NOT NULL,
    issue_datetime TEXT NOT NULL,
    expected_return_datetime TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('issued','overdue','returned','lost')),

    FOREIGN KEY(student_id) REFERENCES students(id),
    FOREIGN KEY(admin_id) REFERENCES admins(id)
)
""")

# issue_items allows multiple equipment per issue
conn.execute("""
CREATE TABLE IF NOT EXISTS issue_items (
    id TEXT PRIMARY KEY,
    issue_id TEXT NOT NULL,
    equipment_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),

    FOREIGN KEY(issue_id) REFERENCES issue_transactions(issue_id),
    FOREIGN KEY(equipment_id) REFERENCES equipment(id)
)
""")

# return_transactions tracks returns
conn.execute("""
CREATE TABLE IF NOT EXISTS return_transactions (
    issue_id TEXT PRIMARY KEY,
    admin_id TEXT NOT NULL,
    return_datetime TEXT NOT NULL,
    equipment_condition TEXT CHECK(equipment_condition IN ('good','damaged','lost')),
    loss_or_damage_report TEXT,

    FOREIGN KEY(issue_id) REFERENCES issue_transactions(issue_id),
    FOREIGN KEY(admin_id) REFERENCES admins(id)
)
""")

# index for faster student lookup
conn.execute("CREATE INDEX IF NOT EXISTS idx_issue_student ON issue_transactions(student_id)")

# index for status filtering
conn.execute("CREATE INDEX IF NOT EXISTS idx_issue_status ON issue_transactions(status)")

# index for equipment category filtering
conn.execute("CREATE INDEX IF NOT EXISTS idx_equipment_category ON equipment(category)")

conn.commit()
conn.close()