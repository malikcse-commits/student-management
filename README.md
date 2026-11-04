# EduManage — Student Management System

A responsive Flask + SQLite student management project designed for learning and diploma-project demonstrations.

## Features
- Admin login with hashed password
- Dashboard counts: students, courses, today's present/absent/late, marks, attendance percentage
- Student add/edit/delete/search
- Course add/edit/delete
- Daily attendance entry (Present / Absent / Late)
- Marks entry and deletion
- Student CSV export
- Responsive layout for phone and desktop

## Run on a computer
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run `pip install -r requirements.txt`
4. Run `python app.py`
5. Visit `http://127.0.0.1:5000`

Default demo login:
- Username: `admin`
- Password: `admin123`

Change the password before sharing or deploying. Set environment variable `ADMIN_PASSWORD` before the first run. The initial admin account is created once; changing the environment variable later will not reset an existing password.

## Deploy
This project includes a Render blueprint (`render.yaml`) and `Procfile`.
1. Create a GitHub repository and upload the project files.
2. In Render, create a new Web Service from that repository.
3. Set `SECRET_KEY` to a long random value and `ADMIN_PASSWORD` to a strong password.
4. Important: SQLite files on many free hosting services may be temporary and can be lost after redeploy/restart. This setup is suitable for a demo; for persistent online records, connect a managed PostgreSQL database or use hosting with persistent storage before using real student data.

## Important
- This is a demonstration/educational app, not a production school information system.
- Do not enter real student personal data into a public demo.
- Add CSRF protection, role permissions, audit logs, backups, HTTPS/domain controls and stronger deployment configuration before real institutional use.
