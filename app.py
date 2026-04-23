import os
from datetime import timedelta
from functools import wraps
import math
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pattern
import bcrypt
from flask_wtf.csrf import CSRFProtect
from db import connect_db, get_ist_timestamp, init_app
app = Flask(__name__)
# Secret key
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key_dev_mode')
app.config["DATABASE"] = os.path.join(app.root_path, "basedata.db")
csrf = CSRFProtect(app)

init_app(app)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in to the page', 'warning')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    conn = connect_db(app)
    items = conn.execute("SELECT * FROM equipment WHERE is_active = 1 ORDER BY category, name").fetchall()
    
    stats = {
        'total_types': len(items),
        'total_items': sum(i['total_quantity'] for i in items),
        'available_items': sum(i['available_quantity'] for i in items),
    }
    stats['issued_items'] = stats['total_items'] - stats['available_items']
    
    conn.close()
    return render_template("home.html", items=items, stats=stats)


@app.route('/login.html')
@app.route('/login_page')
def login_page():
    return render_template('login.html')


@app.route('/login', methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    conn = connect_db(app)
    data = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
    conn.close()
    
    if data and bcrypt.checkpw(password.encode('utf-8'), data['password'].encode('utf-8')):
        session['admin_id'] = data['id']
        return redirect(url_for('dashboard'))
    
    flash('Invalid credentials', 'danger')
    return redirect(url_for('login_page'))


@app.route('/logout')
def logout():
    session.pop('admin_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login_page'))


@app.route('/dashboard')
@login_required
def dashboard():
    conn = connect_db(app)
    items = conn.execute("SELECT * FROM equipment WHERE is_active = 1").fetchall()
    
    stats = {
        'total_types': len(items),
        'total_items': sum(i['total_quantity'] for i in items),
        'available_items': sum(i['available_quantity'] for i in items),
    }
    stats['issued_items'] = stats['total_items'] - stats['available_items']
    
    conn.close()
    return render_template("dashboard.html", stats=stats)


@app.route('/equipment')
@login_required
def equipment():
    conn = connect_db(app)
    items = conn.execute("SELECT * FROM equipment WHERE is_active = 1 ORDER BY category, name").fetchall()
    conn.close()
    return render_template("equipment.html", items=items)


@app.route('/add_equipment', methods=["POST"])
@login_required
def add_equipment():
    name = request.form.get("name", "").strip()
    qty = int(request.form.get("qty", 0) or 0)
    category = request.form.get("category", "").strip()

    if not name:
        flash('Please provide an equipment name.', 'danger')
        return redirect(url_for('equipment'))

    if qty <= 0:
        flash('Quantity must be at least 1.', 'danger')
        return redirect(url_for('equipment'))

    conn = connect_db(app)
    # Duplicate check
    existing = conn.execute(
        "SELECT * FROM equipment WHERE LOWER(name) = LOWER(?) AND is_active = 1", (name,)
    ).fetchone()

    if existing:
        new_total = existing['total_quantity'] + qty
        new_available = existing['available_quantity'] + qty
        conn.execute(
            "UPDATE equipment SET total_quantity=?, available_quantity=? WHERE id=?",
            (new_total, new_available, existing['id'])
        )
        conn.commit()
        conn.close()
        flash(f'"{existing["name"]}" already exists — added {qty} to stock. New total: {new_total}.', 'info')
    else:
        conn.execute(
            "INSERT INTO equipment (name, total_quantity, available_quantity, category) VALUES (?, ?, ?, ?)",
            (name, qty, qty, category)
        )
        conn.commit()
        conn.close()
        flash('Equipment added successfully.', 'success')

    return redirect(url_for('equipment'))


@app.route('/delete_equipment/<int:eq_id>', methods=['POST'])
@login_required
def delete_equipment(eq_id):
    conn = connect_db(app)
    active = conn.execute(
        """SELECT COUNT(*) FROM issue_items ii
           JOIN issue_transactions it ON ii.issue_id = it.issue_id
           WHERE ii.equipment_id = ? AND it.status = 'issued'""",
        (eq_id,)
    ).fetchone()[0]
    
    if active > 0:
        conn.close()
        flash('Cannot delete — this equipment has active issues that have not been returned yet.', 'danger')
        return redirect(url_for('equipment'))
        
    # Soft delete
    conn.execute("UPDATE equipment SET is_active = 0 WHERE id=?", (eq_id,))
    conn.commit()
    conn.close()
    flash('Equipment deleted.', 'success')
    return redirect(url_for('equipment'))


@app.route('/update_equipment_qty/<int:eq_id>', methods=['POST'])
@login_required
def update_equipment_qty(eq_id):
    new_total = request.form.get('new_total', type=int)
    conn = connect_db(app)
    item = conn.execute("SELECT * FROM equipment WHERE id=? AND is_active=1", (eq_id,)).fetchone()
    if not item:
        conn.close()
        flash('Equipment not found.', 'danger')
        return redirect(url_for('equipment'))

    issued_qty = item['total_quantity'] - item['available_quantity']  # Current out
    if new_total is None or new_total < issued_qty:
        conn.close()
        flash(f'Total quantity cannot be less than currently issued amount ({issued_qty}).', 'danger')
        return redirect(url_for('equipment'))

    new_available = new_total - issued_qty
    conn.execute(
        "UPDATE equipment SET total_quantity=?, available_quantity=? WHERE id=?",
        (new_total, new_available, eq_id)
    )
    conn.commit()
    conn.close()
    flash(f'Stock updated for "{item["name"]}": total={new_total}, available={new_available}.', 'success')
    return redirect(url_for('equipment'))


@app.route('/issue', methods=["GET", "POST"])
@login_required
def issue():
    conn = connect_db(app)

    if request.method == 'POST':
        student_id = request.form.get('student_id')
        equipment_id = request.form.get('equipment_id')
        quantity = int(request.form.get('quantity', 1) or 1)

        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        equipment_item = conn.execute("SELECT * FROM equipment WHERE id=? AND is_active=1", (equipment_id,)).fetchone()

        if not student:
            flash('Student not found. Please scan a valid student ID barcode.', 'danger')
            conn.close()
            return redirect(url_for('issue'))

        if not equipment_item:
            flash('Equipment not found. Please select a valid item.', 'danger')
            conn.close()
            return redirect(url_for('issue'))

        if equipment_item['available_quantity'] < quantity:
            flash('Insufficient equipment quantity available.', 'warning')
            conn.close()
            return redirect(url_for('issue'))

        issue_id = pattern.get_issue_id(student_id)
        issue_dt = get_ist_timestamp()
        
        if student_id.upper() in ["24261A05A5", "24261A05B5"]:
            expected_return_str = "N/A"
        else:
            expected_return_dt = issue_dt + timedelta(days=7)
            expected_return_str = expected_return_dt.strftime('%Y-%m-%d %H:%M:%S')

        admin_id = session.get('admin_id', 'unknown')

        conn.execute(
            "INSERT INTO issue_transactions (issue_id, student_id, admin_id, issue_datetime, expected_return_datetime, status) VALUES (?, ?, ?, ?, ?, ?)",
            (issue_id, student_id, admin_id, issue_dt.strftime('%Y-%m-%d %H:%M:%S'), expected_return_str, 'issued')
        )
        conn.execute(
            "INSERT INTO issue_items (id, issue_id, equipment_id, quantity) VALUES (?, ?, ?, ?)",
            (f"{issue_id}_item", issue_id, equipment_id, quantity)
        )
        conn.execute("UPDATE equipment SET available_quantity = available_quantity - ? WHERE id=?", (quantity, equipment_id))
        conn.commit()
        conn.close()

        flash('Equipment issued successfully.', 'success')
        return redirect(url_for('reports'))

    equipment_list = conn.execute("SELECT * FROM equipment WHERE is_active=1 ORDER BY category, name").fetchall()
    student_id = request.args.get('student_id')
    student = None
    if student_id:
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id.upper(),)).fetchone()
        if not student:
            flash(f'Student ID "{student_id}" not found in the database.', 'danger')
        elif student['id'] in ["24261A05A5", "24261A05B5"]:
            # Check arrival
            if request.method == 'GET':
                flash(f'Welcome Creator, {student["name"]}!', 'info')

    conn.close()
    return render_template('issue.html', equipment=equipment_list, student=student)


@app.route('/return', methods=['GET', 'POST'])
@login_required
def return_equipment():
    conn = connect_db(app)

    if request.method == 'POST':
        issue_id = request.form.get('issue_id')
        condition = request.form.get('condition', 'good')  # Status
        damage_report = request.form.get('damage_report', '').strip() or None

        issue = conn.execute("SELECT * FROM issue_transactions WHERE issue_id=?", (issue_id,)).fetchone()
        issue_items = conn.execute("SELECT * FROM issue_items WHERE issue_id=?", (issue_id,)).fetchall()

        if not issue or issue['status'] != 'issued':
            flash('Issue record not found or already returned.', 'warning')
            conn.close()
            return redirect(url_for('return_equipment'))

        for item in issue_items:
            if condition == 'lost':
                # Lost items
                conn.execute(
                    "UPDATE equipment SET total_quantity = total_quantity - ?, available_quantity = MAX(0, available_quantity) WHERE id=?",
                    (item['quantity'], item['equipment_id'])
                )
            else:
                # Restore items
                conn.execute(
                    "UPDATE equipment SET available_quantity = available_quantity + ? WHERE id=?",
                    (item['quantity'], item['equipment_id'])
                )

        new_status = 'lost' if condition == 'lost' else 'returned'
        admin_id = session.get('admin_id', 'unknown')
        
        conn.execute("UPDATE issue_transactions SET status=? WHERE issue_id=?", (new_status, issue_id))
        conn.execute(
            """INSERT OR REPLACE INTO return_transactions
               (issue_id, admin_id, return_datetime, equipment_condition, loss_or_damage_report)
               VALUES (?, ?, ?, ?, ?)""",
            (issue_id, admin_id, get_ist_timestamp().strftime('%Y-%m-%d %H:%M:%S'), condition, damage_report)
        )
        conn.commit()
        conn.close()

        if condition == 'lost':
            flash('Record closed as LOST. Equipment stock', 'warning')
        elif condition == 'damaged':
            flash('Returned and marked as DAMAGED.', 'warning')
        else:
            flash('Returned successfully.', 'success')
        return redirect(url_for('dashboard'))

    student_id = request.args.get('student_id')
    student = None
    issues = []
    if student_id:
        student = conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        if student:
            issues = conn.execute(
                """SELECT ii.issue_id, e.name as equipment_name, i.quantity
                   FROM issue_transactions ii
                   JOIN issue_items i ON ii.issue_id = i.issue_id
                   JOIN equipment e ON i.equipment_id = e.id
                   WHERE ii.status='issued' AND ii.student_id=?""",
                (student_id,)
            ).fetchall()
        else:
            flash(f'Student ID "{student_id}" not found.', 'danger')
    else:
        issues = conn.execute(
            """SELECT ii.issue_id, e.name as equipment_name, i.quantity
               FROM issue_transactions ii
               JOIN issue_items i ON ii.issue_id = i.issue_id
               JOIN equipment e ON i.equipment_id = e.id
               WHERE ii.status='issued'"""
        ).fetchall()

    conn.close()
    return render_template('return.html', issues=issues, student=student)


@app.route('/reports')
@login_required
def reports():
    conn = connect_db(app)
    
    page = request.args.get('page', 1, type=int)
    student_filter = request.args.get('student_id', '').strip()
    status_filter = request.args.get('status', '').strip()
    per_page = 20

   
    where_clauses = []
    params = []

    if student_filter:
        where_clauses.append("it.student_id LIKE ?")
        params.append(f"%{student_filter}%")
    
    if status_filter and status_filter != 'all':
        where_clauses.append("it.status = ?")
        params.append(status_filter)

    where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    count_query = f"""
        SELECT COUNT(*)
        FROM issue_transactions it
        JOIN issue_items ii ON it.issue_id = ii.issue_id
        JOIN equipment e ON ii.equipment_id = e.id
        JOIN students s ON it.student_id = s.id
        LEFT JOIN return_transactions rt ON it.issue_id = rt.issue_id
        {where_str}
    """
    total_records = conn.execute(count_query, params).fetchone()[0]
    total_pages = math.ceil(total_records / per_page) if total_records > 0 else 1
    offset = (page - 1) * per_page

    query = f"""
    SELECT
        it.issue_id,
        it.student_id,
        s.name AS student_name,
        e.name AS equipment_name,
        ii.quantity,
        it.issue_datetime,
        it.expected_return_datetime,
        it.status,
        rt.equipment_condition,
        rt.loss_or_damage_report,
        rt.return_datetime,
        it.admin_id
    FROM issue_transactions it
    JOIN issue_items ii ON it.issue_id = ii.issue_id
    JOIN equipment e ON ii.equipment_id = e.id
    JOIN students s ON it.student_id = s.id
    LEFT JOIN return_transactions rt ON it.issue_id = rt.issue_id
    {where_str}
    ORDER BY it.issue_datetime DESC
    LIMIT ? OFFSET ?
    """
    
    data = conn.execute(query, params + [per_page, offset]).fetchall()
    conn.close()
    
    return render_template(
        'reports.html', 
        reports=data,
        page=page,
        total_pages=total_pages,
        student_filter=student_filter,
        status_filter=status_filter
    )


if __name__ == '__main__':
    app.run(debug=True)
