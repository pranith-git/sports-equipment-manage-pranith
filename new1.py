import sqlite3
conn = sqlite3.connect("basedata.db")

conn.execute("Insert into students(id, name, email, phone, department, year) VALUES ('24261A05A7', 'Sidhartha', 'sidhartha@example.com', '1234567890', 'Computer Science', 2)")
conn.execute("Insert into students(id, name, email, phone, department, year) VALUES ('24261A05A8', 'Ananya', 'ananya@example.com', '0987654321', 'Computer Science', 2)")
conn.commit()
conn.close()