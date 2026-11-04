import os
import sqlite3
from datetime import date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, Response
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(APP_DIR, "edumanage.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-deployment")

def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL,
        duration TEXT DEFAULT '',
        description TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        course_id INTEGER,
        year TEXT DEFAULT '1st Year',
        joined_on TEXT DEFAULT '',
        FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        attendance_date TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Present','Absent','Late')),
        UNIQUE(student_id, attendance_date),
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS marks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        exam_name TEXT NOT NULL,
        marks_obtained REAL NOT NULL,
        total_marks REAL NOT NULL,
        exam_date TEXT DEFAULT '',
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    """)
    if not db.execute("SELECT id FROM users WHERE username='admin'").fetchone():
        password = os.environ.get("ADMIN_PASSWORD", "admin123")
        db.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                   ("admin", generate_password_hash(password)))
    db.commit()

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

@app.before_request
def ensure_database():
    init_db()

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    today = date.today().isoformat()
    stats = {
        "students": db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "courses": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "present": db.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=? AND status='Present'", (today,)).fetchone()[0],
        "absent": db.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=? AND status='Absent'", (today,)).fetchone()[0],
        "late": db.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=? AND status='Late'", (today,)).fetchone()[0],
        "marks": db.execute("SELECT COUNT(*) FROM marks").fetchone()[0],
    }
    marked = stats["present"] + stats["absent"] + stats["late"]
    stats["attendance_pct"] = round((stats["present"] + stats["late"]) * 100 / marked) if marked else 0
    recent = db.execute("""SELECT s.*, c.name AS course_name FROM students s
                          LEFT JOIN courses c ON c.id=s.course_id
                          ORDER BY s.id DESC LIMIT 6""").fetchall()
    return render_template("dashboard.html", stats=stats, recent=recent, today=today)

@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "delete":
            db.execute("DELETE FROM students WHERE id=?", (request.form.get("id"),))
            db.commit()
            flash("Student deleted.", "success")
            return redirect(url_for("students"))
        sid = request.form.get("id")
        values = (
            request.form.get("roll_no","").strip(), request.form.get("name","").strip(),
            request.form.get("email","").strip(), request.form.get("phone","").strip(),
            request.form.get("course_id") or None, request.form.get("year","1st Year"),
            request.form.get("joined_on","")
        )
        if not values[0] or not values[1]:
            flash("Roll number and student name are required.", "error")
        else:
            try:
                if action == "edit" and sid:
                    db.execute("""UPDATE students SET roll_no=?,name=?,email=?,phone=?,course_id=?,year=?,joined_on=? WHERE id=?""", values + (sid,))
                    flash("Student updated.", "success")
                else:
                    db.execute("""INSERT INTO students(roll_no,name,email,phone,course_id,year,joined_on)
                                  VALUES(?,?,?,?,?,?,?)""", values)
                    flash("Student added.", "success")
                db.commit()
            except sqlite3.IntegrityError:
                flash("That roll number is already in use. Please use a unique roll number.", "error")
        return redirect(url_for("students"))
    q = request.args.get("q","").strip()
    edit_student = None
    edit_id = request.args.get("edit")
    if edit_id:
        edit_student = db.execute("SELECT * FROM students WHERE id=?", (edit_id,)).fetchone()
    if q:
        rows = db.execute("""SELECT s.*, c.name AS course_name FROM students s LEFT JOIN courses c ON c.id=s.course_id
                             WHERE s.name LIKE ? OR s.roll_no LIKE ? OR s.email LIKE ? ORDER BY s.id DESC""",
                          (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    else:
        rows = db.execute("""SELECT s.*, c.name AS course_name FROM students s LEFT JOIN courses c ON c.id=s.course_id
                             ORDER BY s.id DESC""").fetchall()
    courses = db.execute("SELECT * FROM courses ORDER BY name").fetchall()
    return render_template("students.html", students=rows, courses=courses, q=q, edit_student=edit_student)

@app.route("/courses", methods=["GET", "POST"])
@login_required
def courses():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action","add")
        cid = request.form.get("id")
        if action == "delete":
            db.execute("DELETE FROM courses WHERE id=?", (cid,))
            db.commit()
            flash("Course deleted. Students previously assigned to it are kept.", "success")
        else:
            name = request.form.get("name","").strip()
            code = request.form.get("code","").strip().upper()
            duration = request.form.get("duration","").strip()
            description = request.form.get("description","").strip()
            try:
                if action == "edit" and cid:
                    db.execute("UPDATE courses SET name=?,code=?,duration=?,description=? WHERE id=?",
                               (name,code,duration,description,cid))
                    flash("Course updated.", "success")
                elif name and code:
                    db.execute("INSERT INTO courses(name,code,duration,description) VALUES(?,?,?,?)",
                               (name,code,duration,description))
                    flash("Course added.", "success")
                else:
                    flash("Course name and code are required.", "error")
                db.commit()
            except sqlite3.IntegrityError:
                flash("Course code must be unique.", "error")
        return redirect(url_for("courses"))
    rows = db.execute("""SELECT c.*, (SELECT COUNT(*) FROM students s WHERE s.course_id=c.id) AS student_count
                         FROM courses c ORDER BY c.name""").fetchall()
    edit_course = db.execute("SELECT * FROM courses WHERE id=?", (request.args.get("edit"),)).fetchone() if request.args.get("edit") else None
    return render_template("courses.html", courses=rows, edit_course=edit_course)

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    db = get_db()
    selected_date = request.values.get("attendance_date", date.today().isoformat())
    if request.method == "POST":
        student_id = request.form.get("student_id")
        status = request.form.get("status")
        selected_date = request.form.get("attendance_date", date.today().isoformat())
        if status not in ("Present","Absent","Late"):
            flash("Choose a valid attendance status.", "error")
        else:
            db.execute("""INSERT INTO attendance(student_id,attendance_date,status) VALUES(?,?,?)
                          ON CONFLICT(student_id,attendance_date) DO UPDATE SET status=excluded.status""",
                       (student_id, selected_date, status))
            db.commit()
            flash("Attendance saved.", "success")
        return redirect(url_for("attendance", attendance_date=selected_date))
    students = db.execute("""SELECT s.id,s.roll_no,s.name,c.name AS course_name,a.status
                             FROM students s LEFT JOIN courses c ON c.id=s.course_id
                             LEFT JOIN attendance a ON a.student_id=s.id AND a.attendance_date=?
                             ORDER BY s.roll_no""", (selected_date,)).fetchall()
    return render_template("attendance.html", students=students, selected_date=selected_date)

@app.route("/marks", methods=["GET", "POST"])
@login_required
def marks():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action","add")
        mid = request.form.get("id")
        if action == "delete":
            db.execute("DELETE FROM marks WHERE id=?", (mid,))
            db.commit()
            flash("Mark record deleted.", "success")
        else:
            try:
                vals = (request.form.get("student_id"), request.form.get("subject","").strip(),
                        request.form.get("exam_name","").strip(), float(request.form.get("marks_obtained","0")),
                        float(request.form.get("total_marks","0")), request.form.get("exam_date",""))
                if vals[3] < 0 or vals[4] <= 0 or vals[3] > vals[4]:
                    raise ValueError()
                db.execute("""INSERT INTO marks(student_id,subject,exam_name,marks_obtained,total_marks,exam_date)
                              VALUES(?,?,?,?,?,?)""", vals)
                db.commit()
                flash("Marks saved.", "success")
            except (ValueError, TypeError):
                flash("Enter valid marks. Obtained marks cannot exceed total marks.", "error")
        return redirect(url_for("marks"))
    rows = db.execute("""SELECT m.*,s.name AS student_name,s.roll_no FROM marks m
                         JOIN students s ON s.id=m.student_id ORDER BY m.id DESC""").fetchall()
    students = db.execute("SELECT id,roll_no,name FROM students ORDER BY roll_no").fetchall()
    return render_template("marks.html", marks=rows, students=students)

@app.route("/export/students.csv")
@login_required
def export_students():
    rows = get_db().execute("""SELECT s.roll_no,s.name,s.email,s.phone,c.name AS course,s.year,s.joined_on
                               FROM students s LEFT JOIN courses c ON c.id=s.course_id ORDER BY s.roll_no""").fetchall()
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Roll Number","Name","Email","Phone","Course","Year","Joined On"])
    for row in rows:
        writer.writerow(list(row))
    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition":"attachment; filename=students.csv"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
