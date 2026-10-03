import os
import sqlite3
import uuid

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"      # needed for flash messages
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024      # 50 MB upload limit

MATERIAL_TYPES = ["Notes", "Reference Material", "Revision Material", "Question Paper"]
PUBLIC_ENDPOINTS = {"index", "login", "register", "admin_login", "static", "uploaded_file",
                    "toggle_wishlist", "forgot_password", "reset_password"}
# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row            # lets us use row["title"] in templates
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query_db(sql, params=(), one=False):
    """Run a SELECT. Returns a list of rows, or a single row (or None) if one=True."""
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute_db(sql, params=()):
    """Run an INSERT / UPDATE / DELETE."""
    conn = get_db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()



def log_user_activity(user_id, action, description, book_id=None):
    """Records one entry in a user's own activity feed (Instagram-style)."""
    execute_db("""INSERT INTO user_activity (user_id, action, description, book_id)
                  VALUES (?, ?, ?, ?)""", (user_id, action, description, book_id))


def log_admin_activity(admin_id, action, details):
    """Records one entry in the admin audit trail."""
    execute_db("""INSERT INTO admin_activity_log (admin_id, action, details)
                  VALUES (?, ?, ?)""", (admin_id, action, details))

# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def save_pdf(file):
    """Validate and save an uploaded PDF. Returns the stored file name, or None if invalid."""
    original_name = secure_filename(file.filename)
    if not original_name.lower().endswith(".pdf"):
        return None
    header = file.stream.read(5)              # every real PDF starts with "%PDF-"
    file.stream.seek(0)
    if header != b"%PDF-":
        return None
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    file.save(os.path.join(UPLOAD_FOLDER, stored_name))
    return stored_name

def save_cover(file):
    """Validate and save a cover image (JPG, PNG or WEBP, max 2 MB).
    Returns the stored file name, or None if the image is invalid."""
    original_name = secure_filename(file.filename)
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in (".jpg", ".jpeg", ".png", ".webp"):
        return None

    header = file.stream.read(12)                  # first bytes tell the real file type
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > 2 * 1024 * 1024:                     # 2 MB limit
        return None

    is_jpeg = header.startswith(b"\xff\xd8\xff")
    is_png = header.startswith(b"\x89PNG\r\n\x1a\n")
    is_webp = header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if not (is_jpeg or is_png or is_webp):
        return None

    stored_name = f"cover_{uuid.uuid4().hex}{extension}"
    file.save(os.path.join(UPLOAD_FOLDER, stored_name))
    return stored_name

def delete_pdf(file_name):
    if file_name:
        path = os.path.join(UPLOAD_FOLDER, file_name)
        if os.path.exists(path):
            os.remove(path)


def create_sample_pdf(path, title):
    """Write a tiny one-page PDF (no libraries needed) so sample books can be opened."""
    title = title.encode("ascii", "ignore").decode()
    content = (f"BT /F1 24 Tf 72 700 Td ({title}) Tj ET\n"
               "BT /F1 12 Tf 72 665 Td (Sample PDF created for demo purposes.) Tj ET\n"
               "BT /F1 12 Tf 72 645 Td (Upload real PDFs from the Admin panel.) Tj ET")
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n"
    xref_position = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_position}\n%%EOF")
    with open(path, "wb") as f:
        f.write(pdf.encode("latin-1"))

def escape_pdf_text(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_response(title, sections):
    """sections: list of (heading, [line, line, ...]). Builds a one-page PDF as bytes."""
    commands = [f"BT /F1 20 Tf 50 760 Td ({escape_pdf_text(title)}) Tj ET"]
    y = 725
    for heading, lines in sections:
        if y < 60:
            break
        commands.append(f"BT /F1 13 Tf 50 {y} Td ({escape_pdf_text(heading)}) Tj ET")
        y -= 20
        for line in lines:
            if y < 50:
                break
            commands.append(f"BT /F1 10 Tf 60 {y} Td ({escape_pdf_text(line)}) Tj ET")
            y -= 15
        y -= 10
    content = "\n".join(commands)

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n"
    xref_position = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF"
    return pdf.encode("latin-1")


# ---------------------------------------------------------------------------
# Database creation + sample data (runs automatically on startup)
# ---------------------------------------------------------------------------
def init_db():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS books (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            author      TEXT NOT NULL,
            subject     TEXT NOT NULL,
            description TEXT,
            category_id INTEGER NOT NULL,
            pdf_file    TEXT NOT NULL,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        );

        CREATE TABLE IF NOT EXISTS study_materials (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT NOT NULL,
            description   TEXT,
            subject       TEXT NOT NULL,
            exam_name     TEXT NOT NULL,
            material_type TEXT NOT NULL,
            year          INTEGER,
            pdf_file      TEXT NOT NULL,
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );

        
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );

        
        CREATE TABLE IF NOT EXISTS wishlist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            book_id    INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, book_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
        );

        
        CREATE TABLE IF NOT EXISTS reviews (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            book_id    INTEGER NOT NULL,
            rating     INTEGER NOT NULL,
            comment    TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, book_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
        );

        
        CREATE TABLE IF NOT EXISTS support_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            subject    TEXT NOT NULL,
            message    TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'open',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );

        
        CREATE TABLE IF NOT EXISTS reading_history (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            book_id          INTEGER NOT NULL,
            last_accessed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, book_id),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
        );

        
        CREATE TABLE IF NOT EXISTS activity_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            activity_date TEXT NOT NULL,
            UNIQUE (user_id, activity_date),
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );

        
        CREATE TABLE IF NOT EXISTS user_activity (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            action      TEXT NOT NULL,
            description TEXT NOT NULL,
            book_id     INTEGER,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS admin_activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER NOT NULL,
            action     TEXT NOT NULL,
            details    TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_id) REFERENCES users (id) ON DELETE CASCADE
        );

    """)

    # ----- add the cover_image column to the books table (safe to run every time) -----
    book_columns = [row["name"] for row in conn.execute("PRAGMA table_info(books)").fetchall()]
    if "cover_image" not in book_columns:
        conn.execute("ALTER TABLE books ADD COLUMN cover_image TEXT")
        conn.commit()

    # ----- add the category_image column to the categories table (safe to run every time) -----
    category_columns = [row["name"] for row in conn.execute("PRAGMA table_info(categories)").fetchall()]
    if "category_image" not in category_columns:
        conn.execute("ALTER TABLE categories ADD COLUMN category_image TEXT")
        conn.commit()

    
    # ----- add reply columns to support_messages (safe to run every time) -----
    message_columns = [row["name"] for row in conn.execute("PRAGMA table_info(support_messages)").fetchall()]
    for column in ("admin_reply", "replied_at"):
        if column not in message_columns:
            conn.execute(f"ALTER TABLE support_messages ADD COLUMN {column} TEXT")
    conn.commit()

    
    # ----- add security question columns to users (safe to run every time) -----
    security_columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    for column in ("security_question", "security_answer_hash"):
        if column not in security_columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
    conn.commit()

    # ----- add profile columns to the users table (safe to run every time) -----
    user_columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
    for column in ("full_name", "phone", "address", "bio", "profile_photo"):
        if column not in user_columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
    conn.commit()

    
    # ----- add featured + download columns to books (safe to run every time) -----
    book_columns2 = [row["name"] for row in conn.execute("PRAGMA table_info(books)").fetchall()]
    if "is_featured" not in book_columns2:
        conn.execute("ALTER TABLE books ADD COLUMN is_featured INTEGER NOT NULL DEFAULT 0")
    if "download_count" not in book_columns2:
        conn.execute("ALTER TABLE books ADD COLUMN download_count INTEGER NOT NULL DEFAULT 0")
    conn.commit()

    # ----- sample categories -----
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO categories (name, description) VALUES (?, ?)",
            [("Computer Science", "Programming, algorithms and databases"),
             ("Engineering", "Core engineering subjects and handbooks"),
             ("Science", "Physics, chemistry and mathematics"),
             ("Literature", "Novels, poetry and literary studies"),
             ("Business & Economics", "Management, finance and economics")])
        conn.commit()

    # ----- sample books (each gets a generated demo PDF) -----
    if conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0:
        sample_books = [
            ("Python Programming Basics", "Arun Kumar", "Programming", "Computer Science",
             "A beginner-friendly introduction to Python with practical examples."),
            ("Data Structures Made Simple", "Priya Nair", "Data Structures", "Computer Science",
             "Arrays, linked lists, stacks, queues and trees explained step by step."),
            ("Database Systems Fundamentals", "Rahul Menon", "Databases", "Computer Science",
             "Relational design, SQL queries and normalization for students."),
            ("Basics of Electrical Engineering", "Suresh Iyer", "Electrical Engineering", "Engineering",
             "Circuits, machines and power systems for first-year engineers."),
            ("Engineering Mathematics Handbook", "Kavitha Raman", "Mathematics", "Engineering",
             "Calculus, algebra and differential equations with solved problems."),
            ("Physics for Beginners", "Meera Krishnan", "Physics", "Science",
             "Mechanics, waves and optics explained in simple language."),
            ("Modern Poetry Anthology", "Lakshmi Narayanan", "English Literature", "Literature",
             "A curated collection of contemporary poems with commentary."),
            ("Principles of Management", "Vikram Shah", "Management", "Business & Economics",
             "Planning, organizing, leading and controlling in modern organizations."),
        ]
        for number, (title, author, subject, category, description) in enumerate(sample_books, start=1):
            file_name = f"sample-book-{number}.pdf"
            create_sample_pdf(os.path.join(UPLOAD_FOLDER, file_name), title)
            category_id = conn.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()[0]
            conn.execute(
                "INSERT INTO books (title, author, subject, description, category_id, pdf_file) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (title, author, subject, description, category_id, file_name))
        conn.commit()

    # ----- sample study materials -----
    if conn.execute("SELECT COUNT(*) FROM study_materials").fetchone()[0] == 0:
        sample_materials = [
            ("Data Structures Quick Notes", "Chapter-wise revision notes.", "Data Structures", "GATE", "Notes", None),
            ("Operating Systems Reference Guide", "Key concepts and diagrams.", "Operating Systems", "GATE", "Reference Material", None),
            ("Engineering Mathematics Formula Sheet", "All important formulas on one sheet.", "Mathematics", "University Exam", "Revision Material", None),
            ("GATE CS Previous Paper", "Solved question paper.", "Computer Science", "GATE", "Question Paper", 2023),
            ("UPSC Prelims General Studies Paper", "Paper I with answer key.", "General Studies", "UPSC", "Question Paper", 2022),
            ("Engineering Mathematics Paper", "Semester exam question paper.", "Mathematics", "University Exam", "Question Paper", 2023),
        ]
        for number, (title, description, subject, exam, m_type, year) in enumerate(sample_materials, start=1):
            file_name = f"sample-material-{number}.pdf"
            create_sample_pdf(os.path.join(UPLOAD_FOLDER, file_name), title)
            conn.execute(
                "INSERT INTO study_materials (title, description, subject, exam_name, material_type, year, pdf_file) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title, description, subject, exam, m_type, year, file_name))
        conn.commit()

    # ----- default admin account (created only if no admin exists) -----
    if conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("Admin@123"), "admin"))
        conn.commit()


    conn.close()




# ---------------------------------------------------------------------------
# Authentication (username + password)
# ---------------------------------------------------------------------------
def get_current_user():
    """Returns the logged-in user (a row) or None."""
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return query_db("""SELECT id, username, role, full_name, phone, address, bio, profile_photo
                       FROM users WHERE id = ?""", (user_id,), one=True)

@app.context_processor
def inject_current_user():
    """Makes `current_user` available in every template (the navbar uses it)."""
    return {"current_user": get_current_user()}


@app.before_request
def protect_admin_area():
    """Runs before every request. Only a logged-in admin can open /admin pages."""
    is_admin_url = request.path == "/admin" or request.path.startswith("/admin/")
    if not is_admin_url or request.path == "/admin/login":
        return None

    user = get_current_user()
    if user is None:
        flash("Please log in as admin to continue.", "error")
        return redirect(url_for("admin_login"))
    if user["role"] != "admin":
        flash("Admin access only.", "error")
        return redirect(url_for("index"))
    return None

def safe_next_url(target):
    """Only allow redirecting back to a page inside this site (blocks open-redirect tricks)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


@app.before_request
def require_login():
    """Every page except Home, Login, Register and files needs a logged-in account."""
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if request.path.startswith("/admin"):
        return None   # /admin pages are already handled by protect_admin_area above

    if get_current_user() is None:
        flash("Please log in to continue.", "error")
        next_target = request.full_path.rstrip("?")
        return redirect(url_for("login", next=next_target))
    return None

@app.route("/register", methods=["GET", "POST"])
def register():
    if get_current_user():
        return redirect(url_for("index"))

    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        error = None
        if not (3 <= len(username) <= 30) or not username.isalpha():
            error = "Username must be 3-30 letters only (no numbers or symbols)." 
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif query_db("SELECT id FROM users WHERE username = ?", (username,), one=True):
            error = "This username is already taken."

        if error:
            flash(error, "error")
        else:
            execute_db("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                       (username, generate_password_hash(password)))
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html", username=username)


def handle_login(admin_only):
    """Used by both the user login page and the admin login page."""
    current = get_current_user()
    if current:
        if current["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        if not admin_only:
            return redirect(url_for("index"))

    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query_db("SELECT * FROM users WHERE username = ?", (username,), one=True)

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect username or password.", "error")
        elif admin_only and user["role"] != "admin":
            flash("This account does not have admin access.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome, {user['username']}!", "success")
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            next_url = safe_next_url(request.form.get("next") or request.args.get("next"))
            if next_url:
                return redirect(next_url)
            return redirect(url_for("index"))

    return render_template("login.html", admin_login=admin_only, username=username)

@app.route("/login", methods=["GET", "POST"])
def login():
    return handle_login(admin_only=False)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    return handle_login(admin_only=True)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))



@app.route("/profile/export-reading-list")
def export_reading_list():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    reading = query_db("""
        SELECT books.title, books.author, reading_history.last_accessed_at
        FROM reading_history JOIN books ON reading_history.book_id = books.id
        WHERE reading_history.user_id = ? ORDER BY reading_history.last_accessed_at DESC
    """, (user["id"],))
    wishlist_books = query_db("""
        SELECT books.title, books.author FROM wishlist
        JOIN books ON wishlist.book_id = books.id
        WHERE wishlist.user_id = ? ORDER BY wishlist.id DESC
    """, (user["id"],))

    sections = [
        ("Recently Read", [f"- {b['title']} by {b['author']}" for b in reading] or ["No books read yet."]),
        ("Wishlist", [f"- {b['title']} by {b['author']}" for b in wishlist_books] or ["Wishlist is empty."]),
    ]
    pdf_bytes = build_pdf_response(f"{user['username']}'s Reading List", sections)

    from flask import Response
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{user["username"]}_reading_list.pdf"'})

@app.route("/profile")
def profile():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    books_read = query_db("SELECT COUNT(DISTINCT book_id) AS c FROM reading_history WHERE user_id = ?",
                          (user["id"],), one=True)["c"]
    reviews_written = query_db("SELECT COUNT(*) AS c FROM reviews WHERE user_id = ?",
                               (user["id"],), one=True)["c"]

    dates = [row["activity_date"] for row in query_db(
        "SELECT activity_date FROM activity_log WHERE user_id = ? ORDER BY activity_date DESC",
        (user["id"],))]
    streak = 0
    if dates:
        from datetime import date, timedelta
        cursor_date = date.today()
        date_set = set(dates)
        # streak counts backward from today; if today has no activity yet, start from yesterday
        if str(cursor_date) not in date_set:
            cursor_date -= timedelta(days=1)
        while str(cursor_date) in date_set:
            streak += 1
            cursor_date -= timedelta(days=1)

    badges = []
    if books_read >= 1:
        badges.append({"icon": "🎯", "name": "First Step", "desc": "Read your first book"})
    if books_read >= 5:
        badges.append({"icon": "📚", "name": "Bookworm", "desc": "Read 5 different books"})
    if books_read >= 10:
        badges.append({"icon": "🎓", "name": "Scholar", "desc": "Read 10 different books"})
    if reviews_written >= 1:
        badges.append({"icon": "✍️", "name": "Reviewer", "desc": "Wrote your first review"})
    if streak >= 3:
        badges.append({"icon": "🔥", "name": "3-Day Streak", "desc": "Visited 3 days in a row"})
    if streak >= 7:
        badges.append({"icon": "⚡", "name": "7-Day Streak", "desc": "Visited 7 days in a row"})

    return render_template("profile.html", books_read=books_read, streak=streak, badges=badges)


@app.route("/settings")
def settings():
    if get_current_user() is None:
        return redirect(url_for("login"))
    return render_template("settings.html")


@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        bio = request.form.get("bio", "").strip()

        error = None
        digits_only = phone.replace(" ", "").replace("-", "")
        if len(full_name) > 100:
            error = "Name is too long."
        elif phone and not (digits_only.isdigit() and 7 <= len(digits_only) <= 15):
            error = "Enter a valid phone number (digits only, 7-15 digits)."
        elif len(address) > 300:
            error = "Address is too long."
        elif len(bio) > 300:
            error = "About section is too long (max 300 characters)."

        if error:
            flash(error, "error")
            return redirect(url_for("edit_profile"))

        execute_db("UPDATE users SET full_name = ?, phone = ?, address = ?, bio = ? WHERE id = ?",
                   (full_name, phone, address, bio, user["id"]))
        flash("Profile updated.", "success")
        return redirect(url_for("profile"))

    return render_template("profile-edit.html")



@app.route("/settings/password", methods=["GET", "POST"])
def change_password():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        full_user = query_db("SELECT * FROM users WHERE id = ?", (user["id"],), one=True)

        error = None
        if not check_password_hash(full_user["password_hash"], current_password):
            error = "Current password is incorrect."
        elif len(new_password) < 6:
            error = "New password must be at least 6 characters."
        elif new_password != confirm_password:
            error = "New passwords do not match."
        elif check_password_hash(full_user["password_hash"], new_password):
            error = "New password must be different from the current password."

        if error:
            flash(error, "error")
            return redirect(url_for("change_password"))

        execute_db("UPDATE users SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(new_password), user["id"]))
        flash("Password changed successfully.", "success")
        return redirect(url_for("settings"))

    return render_template("settings-password.html")



@app.route("/settings/security", methods=["GET", "POST"])
def security_question():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        answer = request.form.get("answer", "").strip()
        current_password = request.form.get("current_password", "")

        full_user = query_db("SELECT * FROM users WHERE id = ?", (user["id"],), one=True)
        error = None
        if not check_password_hash(full_user["password_hash"], current_password):
            error = "Current password is incorrect."
        elif not question or not answer:
            error = "Please fill in both the question and the answer."
        elif len(question) > 150:
            error = "Question is too long."

        if error:
            flash(error, "error")
        else:
            execute_db("UPDATE users SET security_question = ?, security_answer_hash = ? WHERE id = ?",
                       (question, generate_password_hash(answer.lower().strip()), user["id"]))
            flash("Security question saved.", "success")
        return redirect(url_for("security_question"))

    full_user = query_db("SELECT security_question FROM users WHERE id = ?", (user["id"],), one=True)
    return render_template("settings-security.html", current_question=full_user["security_question"])



@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = query_db("SELECT * FROM users WHERE username = ?", (username,), one=True)

        if user is None or not user["security_question"]:
            flash("No account found with a security question set up. "
                  "Please contact the admin via Help Center.", "error")
            return redirect(url_for("forgot_password"))

        session["reset_user_id"] = user["id"]
        return redirect(url_for("reset_password"))

    return render_template("forgot-password.html")


@app.route("/forgot-password/verify", methods=["GET", "POST"])
def reset_password():
    user_id = session.get("reset_user_id")
    if user_id is None:
        return redirect(url_for("forgot_password"))

    user = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if user is None or not user["security_question"]:
        session.pop("reset_user_id", None)
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        answer = request.form.get("answer", "").strip().lower()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        error = None
        if not check_password_hash(user["security_answer_hash"], answer):
            error = "That answer is not correct."
        elif len(new_password) < 6:
            error = "New password must be at least 6 characters."
        elif new_password != confirm_password:
            error = "Passwords do not match."

        if error:
            flash(error, "error")
            return redirect(url_for("reset_password"))

        execute_db("UPDATE users SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(new_password), user["id"]))
        session.pop("reset_user_id", None)
        flash("Password reset successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("forgot-password-verify.html", question=user["security_question"])



@app.route("/settings/delete-account", methods=["POST"])
def delete_account():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    full_user = query_db("SELECT * FROM users WHERE id = ?", (user["id"],), one=True)
    password = request.form.get("password", "")

    if not check_password_hash(full_user["password_hash"], password):
        flash("Incorrect password. Account was not deleted.", "error")
        return redirect(url_for("settings"))

    if user["role"] == "admin":
        flash("Admin accounts cannot be deleted here.", "error")
        return redirect(url_for("settings"))

    delete_pdf(user["profile_photo"])
    execute_db("DELETE FROM users WHERE id = ?", (user["id"],))
    session.clear()
    flash("Your account has been deleted.", "success")
    return redirect(url_for("index"))



@app.route("/help", methods=["GET", "POST"])
def help_center():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if not subject or not message:
            flash("Please fill in both subject and message.", "error")
        elif len(message) > 1000:
            flash("Message is too long (maximum 1000 characters).", "error")
        else:
            execute_db("INSERT INTO support_messages (user_id, subject, message) VALUES (?, ?, ?)",
                       (user["id"], subject, message))
            flash("Your message has been sent to the admin. We'll get back to you soon.", "success")
        return redirect(url_for("help_center"))

    my_messages = query_db("""
        SELECT * FROM support_messages WHERE user_id = ? ORDER BY created_at DESC
    """, (user["id"],))
    return render_template("help.html", my_messages=my_messages)


@app.route("/admin/messages")
def admin_messages():
    messages = query_db("""
        SELECT support_messages.*, users.username
        FROM support_messages JOIN users ON support_messages.user_id = users.id
        ORDER BY support_messages.status ASC, support_messages.created_at DESC
    """)
    return render_template("admin-messages.html", messages=messages)


@app.route("/admin/messages/<int:message_id>/resolve", methods=["POST"])
def resolve_message(message_id):
    if query_db("SELECT id FROM support_messages WHERE id = ?", (message_id,), one=True) is None:
        abort(404)
    execute_db("UPDATE support_messages SET status = 'resolved' WHERE id = ?", (message_id,))
    log_admin_activity(get_current_user()["id"], "resolve_message", f"Marked message #{message_id} as resolved")
    flash("Message marked as resolved.", "success")
    return redirect(url_for("admin_messages"))

@app.route("/admin/messages/<int:message_id>/reply", methods=["POST"])
def reply_to_message(message_id):
    message = query_db("SELECT id FROM support_messages WHERE id = ?", (message_id,), one=True)
    if message is None:
        abort(404)

    reply = request.form.get("admin_reply", "").strip()
    if not reply:
        flash("Reply cannot be empty.", "error")
        return redirect(url_for("admin_messages"))
    if len(reply) > 1000:
        flash("Reply is too long (maximum 1000 characters).", "error")
        return redirect(url_for("admin_messages"))

    execute_db("""UPDATE support_messages
                  SET admin_reply = ?, replied_at = CURRENT_TIMESTAMP, status = 'resolved'
                  WHERE id = ?""", (reply, message_id))
    flash("Reply sent to the user.", "success")
    return redirect(url_for("admin_messages"))


@app.route("/admin/messages/<int:message_id>/delete", methods=["POST"])
def delete_message(message_id):
    if query_db("SELECT id FROM support_messages WHERE id = ?", (message_id,), one=True) is None:
        abort(404)
    execute_db("DELETE FROM support_messages WHERE id = ?", (message_id,))
    flash("Message deleted.", "success")
    return redirect(url_for("admin_messages"))



@app.route("/admin/activity")
def admin_activity():
    logs = query_db("""
        SELECT admin_activity_log.*, users.username
        FROM admin_activity_log JOIN users ON admin_activity_log.admin_id = users.id
        ORDER BY admin_activity_log.created_at DESC LIMIT 100
    """)
    return render_template("admin-activity.html", logs=logs)



@app.route("/admin/student-activity")
def admin_student_activity():
    students = query_db("SELECT id, username FROM users WHERE role = 'user' ORDER BY username")
    downloads = query_db("""
        SELECT user_activity.user_id, books.title, user_activity.created_at
        FROM user_activity JOIN books ON user_activity.book_id = books.id
        WHERE user_activity.action = 'download'
        ORDER BY user_activity.created_at DESC
    """)
    wishlists = query_db("""
        SELECT wishlist.user_id, books.title, wishlist.created_at
        FROM wishlist JOIN books ON wishlist.book_id = books.id
        ORDER BY wishlist.id DESC
    """)

    report = []
    for student in students:
        report.append({
            "username": student["username"],
            "downloads": [r for r in downloads if r["user_id"] == student["id"]],
            "wishlist": [r for r in wishlists if r["user_id"] == student["id"]],
        })

    return render_template("admin-student-activity.html", report=report)


@app.route("/admin/student-activity/export")
def export_student_activity():
    import csv
    import io
    from flask import Response

    rows = query_db("""
        SELECT users.username, 'Download' AS kind, books.title, user_activity.created_at AS activity_date
        FROM user_activity
        JOIN users ON user_activity.user_id = users.id
        JOIN books ON user_activity.book_id = books.id
        WHERE user_activity.action = 'download'
        UNION ALL
        SELECT users.username, 'Wishlist' AS kind, books.title, wishlist.created_at AS activity_date
        FROM wishlist
        JOIN users ON wishlist.user_id = users.id
        JOIN books ON wishlist.book_id = books.id
        ORDER BY activity_date DESC
    """)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Username", "Activity Type", "Book Title", "Date"])
    for row in rows:
        writer.writerow([row["username"], row["kind"], row["title"], row["activity_date"]])

    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=student_activity_report.csv"})

@app.route("/profile/photo", methods=["POST"])
def update_profile_photo():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))

    photo = request.files.get("photo")
    if request.form.get("remove_photo"):
        delete_pdf(user["profile_photo"])
        execute_db("UPDATE users SET profile_photo = NULL WHERE id = ?", (user["id"],))
        flash("Profile photo removed.", "success")
    elif photo and photo.filename:
        photo_name = save_cover(photo)
        if photo_name is None:
            flash("Invalid image. Use JPG, PNG or WEBP, maximum 2 MB.", "error")
        else:
            delete_pdf(user["profile_photo"])
            execute_db("UPDATE users SET profile_photo = ? WHERE id = ?", (photo_name, user["id"]))
            flash("Profile photo updated.", "success")
    else:
        flash("Please choose a photo, or tick remove.", "error")
    return redirect(url_for("profile"))

@app.context_processor
def inject_wishlist_ids():
    """Gives every template the list of book ids this user has hearted."""
    user = get_current_user()
    if user is None:
        return {"wishlist_ids": []}
    rows = query_db("SELECT book_id FROM wishlist WHERE user_id = ?", (user["id"],))
    return {"wishlist_ids": [row["book_id"] for row in rows]}


@app.route("/wishlist")
def wishlist():
    user = get_current_user()
    if user is None:
        flash("Please log in to see your wishlist.", "error")
        return redirect(url_for("login"))
    saved_books = query_db("""
        SELECT books.*, categories.name AS category_name
        FROM wishlist
        JOIN books ON wishlist.book_id = books.id
        JOIN categories ON books.category_id = categories.id
        WHERE wishlist.user_id = ?
        ORDER BY wishlist.id DESC
    """, (user["id"],))
    return render_template("wishlist.html", books=saved_books)


@app.route("/wishlist/toggle/<int:book_id>", methods=["POST"])
def toggle_wishlist(book_id):
    """Heart clicked: add the book if it is not in the wishlist, remove it if it is."""
    user = get_current_user()
    if user is None:
        return jsonify(error="login_required"), 401
    book = query_db("SELECT id, title FROM books WHERE id = ?", (book_id,), one=True)
    if book is None:
        return jsonify(error="not_found"), 404

    existing = query_db("SELECT id FROM wishlist WHERE user_id = ? AND book_id = ?",
                        (user["id"], book_id), one=True)
    if existing:
        execute_db("DELETE FROM wishlist WHERE id = ?", (existing["id"],))
        log_user_activity(user["id"], "wishlist_remove", f"Removed \"{book['title']}\" from wishlist", book_id)
        return jsonify(wishlisted=False)
    execute_db("INSERT INTO wishlist (user_id, book_id) VALUES (?, ?)", (user["id"], book_id))
    log_user_activity(user["id"], "wishlist_add", f"Added \"{book['title']}\" to wishlist", book_id)
    return jsonify(wishlisted=True)



@app.route("/activity")
def my_activity():
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))
    activities = query_db("""
        SELECT user_activity.*, books.title AS book_title
        FROM user_activity LEFT JOIN books ON user_activity.book_id = books.id
        WHERE user_activity.user_id = ?
        ORDER BY user_activity.created_at DESC LIMIT 50
    """, (user["id"],))
    return render_template("activity.html", activities=activities)

@app.route("/books/<int:book_id>/review", methods=["POST"])
def submit_review(book_id):
    user = get_current_user()
    if user is None:
        return redirect(url_for("login"))
    if query_db("SELECT id FROM books WHERE id = ?", (book_id,), one=True) is None:
        abort(404)

    rating = request.form.get("rating", "")
    comment = request.form.get("comment", "").strip()

    if rating not in ("1", "2", "3", "4", "5"):
        flash("Please choose a star rating from 1 to 5.", "error")
        return redirect(url_for("book_details", book_id=book_id))
    if len(comment) > 500:
        flash("Review is too long (maximum 500 characters).", "error")
        return redirect(url_for("book_details", book_id=book_id))

    execute_db("""
        INSERT INTO reviews (user_id, book_id, rating, comment)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, book_id)
        DO UPDATE SET rating = excluded.rating, comment = excluded.comment,
                       updated_at = CURRENT_TIMESTAMP
    """, (user["id"], book_id, int(rating), comment))

    book_row = query_db("SELECT title FROM books WHERE id = ?", (book_id,), one=True)
    log_user_activity(user["id"], "review", f"Rated \"{book_row['title']}\" {rating}★", book_id)
    flash("Thanks! Your review has been saved.", "success")
    return redirect(url_for("book_details", book_id=book_id))


@app.route("/reviews/<int:review_id>/delete", methods=["POST"])
def delete_review(review_id):
    user = get_current_user()
    review = query_db("SELECT * FROM reviews WHERE id = ?", (review_id,), one=True)
    if review is None:
        abort(404)
    if user is None or (user["id"] != review["user_id"] and user["role"] != "admin"):
        flash("You can only delete your own review.", "error")
        return redirect(url_for("book_details", book_id=review["book_id"]))

    execute_db("DELETE FROM reviews WHERE id = ?", (review_id,))
    flash("Review deleted.", "success")
    return redirect(url_for("book_details", book_id=review["book_id"]))

# ---------------------------------------------------------------------------
# Public (user) routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    categories = query_db("""
        SELECT categories.*, COUNT(books.id) AS book_count
        FROM categories LEFT JOIN books ON books.category_id = categories.id
        GROUP BY categories.id ORDER BY categories.name
    """)
    latest_books = query_db("""
        SELECT books.*, categories.name AS category_name,
               r.avg_rating, r.review_count
        FROM books
        JOIN categories ON books.category_id = categories.id
        LEFT JOIN (SELECT book_id, AVG(rating) AS avg_rating, COUNT(*) AS review_count
                   FROM reviews GROUP BY book_id) r ON r.book_id = books.id
        ORDER BY books.id DESC LIMIT 6
    """)
    featured_book = query_db("""
        SELECT books.*, categories.name AS category_name
        FROM books JOIN categories ON books.category_id = categories.id
        WHERE books.is_featured = 1 LIMIT 1
    """, one=True)
    stats = {
        "books": query_db("SELECT COUNT(*) AS c FROM books", one=True)["c"],
        "categories": query_db("SELECT COUNT(*) AS c FROM categories", one=True)["c"],
        "materials": query_db("SELECT COUNT(*) AS c FROM study_materials", one=True)["c"],
    }
    recent_reads = []
    current = get_current_user()
    if current:
        recent_reads = query_db("""
            SELECT books.*, categories.name AS category_name, r.avg_rating, r.review_count,
                   reading_history.last_accessed_at
            FROM reading_history
            JOIN books ON reading_history.book_id = books.id
            JOIN categories ON books.category_id = categories.id
            LEFT JOIN (SELECT book_id, AVG(rating) AS avg_rating, COUNT(*) AS review_count
                       FROM reviews GROUP BY book_id) r ON r.book_id = books.id
            WHERE reading_history.user_id = ?
            ORDER BY reading_history.last_accessed_at DESC LIMIT 4
        """, (current["id"],))
    return render_template("index.html", categories=categories, latest_books=latest_books,
                           stats=stats, recent_reads=recent_reads, featured_book=featured_book)

@app.route("/books")
def books():
    search = request.args.get("q", "").strip()
    category_id = request.args.get("category", "").strip()
    page = request.args.get("page", "1")
    page = int(page) if page.isdigit() and int(page) > 0 else 1
    per_page = 8

    conditions = "WHERE 1 = 1"
    params = []
    if search:
        conditions += " AND (books.title LIKE ? OR books.author LIKE ? OR books.subject LIKE ?)"
        params += [f"%{search}%"] * 3
    if category_id:
        conditions += " AND books.category_id = ?"
        params.append(category_id)

    total_books = query_db(f"""
        SELECT COUNT(*) AS c FROM books
        JOIN categories ON books.category_id = categories.id
        {conditions}
    """, params, one=True)["c"]

    total_pages = max(1, (total_books + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = query_db(f"""
        SELECT books.*, categories.name AS category_name, r.avg_rating, r.review_count
        FROM books
        JOIN categories ON books.category_id = categories.id
        LEFT JOIN (SELECT book_id, AVG(rating) AS avg_rating, COUNT(*) AS review_count
                   FROM reviews GROUP BY book_id) r ON r.book_id = books.id
        {conditions}
        ORDER BY books.id DESC LIMIT ? OFFSET ?
    """, params + [per_page, offset])

    return render_template("books.html",
                           books=rows,
                           categories=query_db("SELECT * FROM categories ORDER BY name"),
                           search=search,
                           selected_category=category_id,
                           page=page,
                           total_pages=total_pages,
                           total_books=total_books)

@app.route("/books/<int:book_id>")
def book_details(book_id):
    book = query_db("""
        SELECT books.*, categories.name AS category_name, r.avg_rating, r.review_count
        FROM books
        JOIN categories ON books.category_id = categories.id
        LEFT JOIN (SELECT book_id, AVG(rating) AS avg_rating, COUNT(*) AS review_count
                   FROM reviews GROUP BY book_id) r ON r.book_id = books.id
        WHERE books.id = ?
    """, (book_id,), one=True)
    if book is None:
        abort(404)

    similar_books = query_db("""
        SELECT books.*, categories.name AS category_name, r.avg_rating, r.review_count
        FROM books
        JOIN categories ON books.category_id = categories.id
        LEFT JOIN (SELECT book_id, AVG(rating) AS avg_rating, COUNT(*) AS review_count
                   FROM reviews GROUP BY book_id) r ON r.book_id = books.id
        WHERE books.category_id = ? AND books.id != ?
        ORDER BY books.id DESC LIMIT 4
    """, (book["category_id"], book_id))

    reviews = query_db("""
        SELECT reviews.*, users.username, users.profile_photo
        FROM reviews JOIN users ON reviews.user_id = users.id
        WHERE reviews.book_id = ? ORDER BY reviews.created_at DESC
    """, (book_id,))

    current = get_current_user()
    my_review = None
    if current:
        my_review = query_db("SELECT * FROM reviews WHERE user_id = ? AND book_id = ?",
                             (current["id"], book_id), one=True)
        execute_db("""
            INSERT INTO reading_history (user_id, book_id, last_accessed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, book_id) DO UPDATE SET last_accessed_at = CURRENT_TIMESTAMP
        """, (current["id"], book_id))
        log_user_activity(current["id"], "view", f"Viewed \"{book['title']}\"", book_id)

    return render_template("book-details.html", book=book, reviews=reviews,
                           my_review=my_review, similar_books=similar_books)


@app.route("/exam-preparation")
def exam_preparation():
    search = request.args.get("q", "").strip()
    exam = request.args.get("exam", "").strip()

    sql = "SELECT * FROM study_materials WHERE 1 = 1"
    params = []
    if search:
        sql += " AND (title LIKE ? OR subject LIKE ?)"
        params += [f"%{search}%"] * 2
    if exam:
        sql += " AND exam_name = ?"
        params.append(exam)
    sql += " ORDER BY year DESC, id DESC"
    materials = query_db(sql, params)

    return render_template(
        "exam-preparation.html",
        study_materials=[m for m in materials if m["material_type"] != "Question Paper"],
        question_papers=[m for m in materials if m["material_type"] == "Question Paper"],
        exams=query_db("SELECT DISTINCT exam_name FROM study_materials ORDER BY exam_name"),
        search=search,
        selected_exam=exam)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """Serves PDFs. The browser's built-in PDF viewer opens them inline."""
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/books/<int:book_id>/download")
def download_book(book_id):
    book = query_db("SELECT * FROM books WHERE id = ?", (book_id,), one=True)
    if book is None:
        abort(404)
    execute_db("UPDATE books SET download_count = download_count + 1 WHERE id = ?", (book_id,))
    current = get_current_user()
    if current:
        log_user_activity(current["id"], "download", f"Downloaded \"{book['title']}\"", book_id)
    return redirect(url_for("uploaded_file", filename=book["pdf_file"]))

@app.route("/api/search-suggestions")
def search_suggestions():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])

    rows = query_db("""
        SELECT id, title, author FROM books
        WHERE title LIKE ? OR author LIKE ?
        ORDER BY title LIMIT 6
    """, (f"%{query}%", f"%{query}%"))

    results = [{"id": row["id"], "title": row["title"], "author": row["author"]} for row in rows]
    return jsonify(results)

# ---------------------------------------------------------------------------
# Admin routes: dashboard and books
# ---------------------------------------------------------------------------
@app.route("/admin")
def admin_dashboard():
    stats = {
        "books": query_db("SELECT COUNT(*) AS c FROM books", one=True)["c"],
        "categories": query_db("SELECT COUNT(*) AS c FROM categories", one=True)["c"],
        "materials": query_db("SELECT COUNT(*) AS c FROM study_materials", one=True)["c"],
        "users": query_db("SELECT COUNT(*) AS c FROM users WHERE role = 'user'", one=True)["c"],
    }
    all_books = query_db("""
        SELECT books.*, categories.name AS category_name
        FROM books JOIN categories ON books.category_id = categories.id
        ORDER BY books.id DESC
    """)
    return render_template("admin.html", stats=stats, books=all_books)


@app.route("/admin/analytics")
def admin_analytics():
    books_per_month = query_db("""
        SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS c
        FROM books GROUP BY month ORDER BY month
    """)
    top_wishlisted = query_db("""
        SELECT books.title, COUNT(wishlist.id) AS c
        FROM wishlist JOIN books ON wishlist.book_id = books.id
        GROUP BY books.id ORDER BY c DESC LIMIT 5
    """)
    top_rated = query_db("""
        SELECT books.title, AVG(reviews.rating) AS avg_rating, COUNT(reviews.id) AS c
        FROM reviews JOIN books ON reviews.book_id = books.id
        GROUP BY books.id HAVING c >= 1 ORDER BY avg_rating DESC LIMIT 5
    """)
    top_downloaded = query_db("""
        SELECT title, download_count FROM books
        WHERE download_count > 0 ORDER BY download_count DESC LIMIT 5
    """)
    summary = {
        "total_downloads": query_db("SELECT COALESCE(SUM(download_count),0) AS c FROM books", one=True)["c"],
        "total_wishlisted": query_db("SELECT COUNT(*) AS c FROM wishlist", one=True)["c"],
        "avg_rating": query_db("SELECT ROUND(AVG(rating),1) AS a FROM reviews", one=True)["a"] or 0,
        "active_students": query_db("SELECT COUNT(DISTINCT user_id) AS c FROM reading_history", one=True)["c"],
    }
    return render_template("admin-analytics.html", summary=summary,
                           months=[r["month"] for r in books_per_month],
                           month_counts=[r["c"] for r in books_per_month],
                           wishlist_labels=[r["title"] for r in top_wishlisted],
                           wishlist_counts=[r["c"] for r in top_wishlisted],
                           rating_labels=[r["title"] for r in top_rated],
                           rating_values=[round(r["avg_rating"], 1) for r in top_rated],
                           download_labels=[r["title"] for r in top_downloaded],
                           download_counts=[r["download_count"] for r in top_downloaded])

def read_book_form():
    return {key: request.form.get(key, "").strip()
            for key in ("title", "author", "subject", "description", "category_id")}


def validate_book_form(data):
    """Returns an error message, or None if the data is valid."""
    if not (data["title"] and data["author"] and data["subject"] and data["category_id"]):
        return "Title, author, subject and category are required."
    if query_db("SELECT id FROM categories WHERE id = ?", (data["category_id"],), one=True) is None:
        return "Please choose a valid category."
    return None

@app.route("/admin/books/add", methods=["GET", "POST"])
def add_book():
    categories = query_db("SELECT * FROM categories ORDER BY name")
    if request.method == "POST":
        data = read_book_form()
        pdf = request.files.get("pdf")
        cover = request.files.get("cover")
        error = validate_book_form(data)
        if error is None and (pdf is None or pdf.filename == ""):
            error = "Please upload a PDF file."

        stored_name = None
        cover_name = None
        if error is None:
            stored_name = save_pdf(pdf)
            if stored_name is None:
                error = "Invalid file. Only real PDF files are allowed."

        # The cover image is optional
        if error is None and cover and cover.filename:
            cover_name = save_cover(cover)
            if cover_name is None:
                delete_pdf(stored_name)          # remove the PDF we just saved
                error = "Invalid cover image. Use JPG, PNG or WEBP, maximum 2 MB."

        if error:
            flash(error, "error")
            return render_template("add-book.html", categories=categories, form=request.form)

        execute_db("""INSERT INTO books
                      (title, author, subject, description, category_id, pdf_file, cover_image)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""",
                   (data["title"], data["author"], data["subject"], data["description"],
                    data["category_id"], stored_name, cover_name))
        log_admin_activity(get_current_user()["id"], "add_book", f"Added book \"{data['title']}\"")
        flash("Book added successfully.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add-book.html", categories=categories, form={})


@app.route("/admin/books/<int:book_id>/edit", methods=["GET", "POST"])
def edit_book(book_id):
    book = query_db("SELECT * FROM books WHERE id = ?", (book_id,), one=True)
    if book is None:
        abort(404)
    categories = query_db("SELECT * FROM categories ORDER BY name")

    if request.method == "POST":
        data = read_book_form()
        pdf = request.files.get("pdf")
        cover = request.files.get("cover")
        error = validate_book_form(data)

        new_pdf_name = None
        new_cover_name = None
        if error is None and pdf and pdf.filename:          # PDF is optional when editing
            new_pdf_name = save_pdf(pdf)
            if new_pdf_name is None:
                error = "Invalid file. Only real PDF files are allowed."

        if error is None and cover and cover.filename:      # cover is optional too
            new_cover_name = save_cover(cover)
            if new_cover_name is None:
                delete_pdf(new_pdf_name)                    # undo the PDF saved above
                error = "Invalid cover image. Use JPG, PNG or WEBP, maximum 2 MB."

        if error:
            flash(error, "error")
            return render_template("edit-book.html", book=book, categories=categories)

        pdf_file = book["pdf_file"]
        if new_pdf_name:
            delete_pdf(book["pdf_file"])                    # remove the old PDF
            pdf_file = new_pdf_name

        cover_image = book["cover_image"]
        if new_cover_name:
            delete_pdf(book["cover_image"])                 # remove the old cover
            cover_image = new_cover_name
        elif request.form.get("remove_cover") and cover_image:
            delete_pdf(cover_image)                         # "Remove cover" was ticked
            cover_image = None

        execute_db("""UPDATE books SET title = ?, author = ?, subject = ?, description = ?,
                      category_id = ?, pdf_file = ?, cover_image = ? WHERE id = ?""",
                   (data["title"], data["author"], data["subject"], data["description"],
                    data["category_id"], pdf_file, cover_image, book_id))
        log_admin_activity(get_current_user()["id"], "edit_book", f"Edited book \"{data['title']}\"")
        flash("Book updated successfully.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("edit-book.html", book=book, categories=categories)

@app.route("/admin/books/<int:book_id>/delete", methods=["POST"])
def delete_book(book_id):
    book = query_db("SELECT * FROM books WHERE id = ?", (book_id,), one=True)
    if book is None:
        abort(404)
    delete_pdf(book["pdf_file"])
    delete_pdf(book["cover_image"])          # also remove the cover image (if any)
    execute_db("DELETE FROM books WHERE id = ?", (book_id,))
    log_admin_activity(get_current_user()["id"], "delete_book", f"Deleted book \"{book['title']}\"")
    flash("Book deleted.", "success")
    return redirect(url_for("admin_dashboard"))



@app.route("/admin/books/bulk-delete", methods=["POST"])
def bulk_delete_books():
    book_ids = request.form.getlist("book_ids")
    if not book_ids:
        flash("No books selected.", "error")
        return redirect(url_for("admin_dashboard"))

    deleted_titles = []
    for book_id in book_ids:
        book = query_db("SELECT * FROM books WHERE id = ?", (book_id,), one=True)
        if book:
            delete_pdf(book["pdf_file"])
            delete_pdf(book["cover_image"])
            execute_db("DELETE FROM books WHERE id = ?", (book_id,))
            deleted_titles.append(book["title"])

    if deleted_titles:
        log_admin_activity(get_current_user()["id"], "bulk_delete",
                           f"Bulk deleted {len(deleted_titles)} books: {', '.join(deleted_titles[:5])}" +
                           ("..." if len(deleted_titles) > 5 else ""))
    flash(f"{len(deleted_titles)} book(s) deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/books/<int:book_id>/feature", methods=["POST"])
def feature_book(book_id):
    book = query_db("SELECT id, title FROM books WHERE id = ?", (book_id,), one=True)
    if book is None:
        abort(404)
    execute_db("UPDATE books SET is_featured = 0")           # only one book featured at a time
    execute_db("UPDATE books SET is_featured = 1 WHERE id = ?", (book_id,))
    log_admin_activity(get_current_user()["id"], "feature_book", f"Set \"{book['title']}\" as Book of the Day")
    flash("Book of the Day updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/books/unfeature", methods=["POST"])
def unfeature_book():
    execute_db("UPDATE books SET is_featured = 0")
    flash("Book of the Day removed.", "success")
    return redirect(url_for("admin_dashboard"))

# ---------------------------------------------------------------------------
# Admin routes: categories
# ---------------------------------------------------------------------------
@app.route("/admin/categories", methods=["GET", "POST"])
def admin_categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        image = request.files.get("image")

        if not name:
            flash("Category name is required.", "error")
        else:
            image_name = None
            error = None
            if image and image.filename:
                image_name = save_cover(image)
                if image_name is None:
                    error = "Invalid image. Use JPG, PNG or WEBP, maximum 2 MB."

            if error:
                flash(error, "error")
            else:
                try:
                    execute_db("INSERT INTO categories (name, description, category_image) VALUES (?, ?, ?)",
                               (name, description, image_name))
                    log_admin_activity(get_current_user()["id"], "add_category", f"Added category \"{name}\"")
                    flash("Category added.", "success")
                except sqlite3.IntegrityError:
                    delete_pdf(image_name)   # undo the saved image; the name was a duplicate
                    flash("A category with this name already exists.", "error")
        return redirect(url_for("admin_categories"))

    categories = query_db("""
        SELECT categories.*, COUNT(books.id) AS book_count
        FROM categories LEFT JOIN books ON books.category_id = categories.id
        GROUP BY categories.id ORDER BY categories.name
    """)
    return render_template("admin-categories.html", categories=categories)

@app.route("/admin/categories/<int:category_id>/image", methods=["POST"])
def update_category_image(category_id):
    category = query_db("SELECT * FROM categories WHERE id = ?", (category_id,), one=True)
    if category is None:
        abort(404)

    image = request.files.get("image")
    if request.form.get("remove_image"):
        delete_pdf(category["category_image"])
        execute_db("UPDATE categories SET category_image = NULL WHERE id = ?", (category_id,))
        flash("Category image removed.", "success")
    elif image and image.filename:
        image_name = save_cover(image)
        if image_name is None:
            flash("Invalid image. Use JPG, PNG or WEBP, maximum 2 MB.", "error")
        else:
            delete_pdf(category["category_image"])
            execute_db("UPDATE categories SET category_image = ? WHERE id = ?",
                       (image_name, category_id))
            flash("Category image updated.", "success")
    else:
        flash("Please choose an image or tick remove.", "error")
    return redirect(url_for("admin_categories"))


@app.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
def delete_category(category_id):
    count = query_db("SELECT COUNT(*) AS c FROM books WHERE category_id = ?",
                     (category_id,), one=True)["c"]
    if count > 0:
        flash("This category still has books. Move or delete them first.", "error")
    else:
        category = query_db("SELECT name, category_image FROM categories WHERE id = ?", (category_id,), one=True)
        delete_pdf(category["category_image"])
        execute_db("DELETE FROM categories WHERE id = ?", (category_id,))
        log_admin_activity(get_current_user()["id"], "delete_category", f"Deleted category \"{category['name']}\"")
        flash("Category deleted.", "success")
        
    return redirect(url_for("admin_categories"))


# ---------------------------------------------------------------------------
# Admin routes: study materials
# ---------------------------------------------------------------------------
@app.route("/admin/materials", methods=["GET", "POST"])
def admin_materials():
    if request.method == "POST":
        form = {key: request.form.get(key, "").strip()
                for key in ("title", "description", "subject", "exam_name", "material_type", "year")}
        pdf = request.files.get("pdf")

        error = None
        year = None
        if not (form["title"] and form["subject"] and form["exam_name"]):
            error = "Title, subject and exam are required."
        elif form["material_type"] not in MATERIAL_TYPES:
            error = "Please choose a valid material type."
        elif form["year"]:
            if form["year"].isdigit() and 1990 <= int(form["year"]) <= 2100:
                year = int(form["year"])
            else:
                error = "Year must be a number between 1990 and 2100."
        if error is None and (pdf is None or pdf.filename == ""):
            error = "Please upload a PDF file."

        stored_name = None
        if error is None:
            stored_name = save_pdf(pdf)
            if stored_name is None:
                error = "Invalid file. Only real PDF files are allowed."

        if error:
            flash(error, "error")
        else:
            execute_db("""INSERT INTO study_materials
                          (title, description, subject, exam_name, material_type, year, pdf_file)
                          VALUES (?, ?, ?, ?, ?, ?, ?)""",
                       (form["title"], form["description"], form["subject"],
                        form["exam_name"], form["material_type"], year, stored_name))
            log_admin_activity(get_current_user()["id"], "add_material", f"Added study material \"{form['title']}\"")
            flash("Study material added.", "success")
        return redirect(url_for("admin_materials"))

    materials = query_db("SELECT * FROM study_materials ORDER BY id DESC")
    return render_template("admin-materials.html", materials=materials, material_types=MATERIAL_TYPES)


@app.route("/admin/materials/<int:material_id>/delete", methods=["POST"])
def delete_material(material_id):
    material = query_db("SELECT * FROM study_materials WHERE id = ?", (material_id,), one=True)
    if material is None:
        abort(404)
    delete_pdf(material["pdf_file"])
    execute_db("DELETE FROM study_materials WHERE id = ?", (material_id,))
    log_admin_activity(get_current_user()["id"], "delete_material", f"Deleted study material \"{material['title']}\"")
    flash("Study material deleted.", "success")
    return redirect(url_for("admin_materials"))

# ---------------------------------------------------------------------------
# Admin routes: registered users
# ---------------------------------------------------------------------------
@app.route("/admin/users")
def admin_users():
    users = query_db("""
        SELECT users.id, users.username, users.role, users.created_at,
               COUNT(wishlist.id) AS wishlist_count
        FROM users LEFT JOIN wishlist ON wishlist.user_id = users.id
        GROUP BY users.id
        ORDER BY users.id DESC
    """)
    return render_template("admin-users.html", users=users)



@app.route("/admin/users/<int:user_id>")
def admin_view_user(user_id):
    user = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if user is None:
        abort(404)

    wishlist_books = query_db("""
        SELECT books.title FROM wishlist JOIN books ON wishlist.book_id = books.id
        WHERE wishlist.user_id = ? ORDER BY wishlist.id DESC
    """, (user_id,))
    reviews = query_db("""
        SELECT reviews.rating, reviews.comment, books.title
        FROM reviews JOIN books ON reviews.book_id = books.id
        WHERE reviews.user_id = ? ORDER BY reviews.created_at DESC
    """, (user_id,))
    downloads = query_db("""
        SELECT books.title, user_activity.created_at
        FROM user_activity JOIN books ON user_activity.book_id = books.id
        WHERE user_activity.user_id = ? AND user_activity.action = 'download'
        ORDER BY user_activity.created_at DESC
    """, (user_id,))

    return render_template("admin-user-details.html", user=user, wishlist_books=wishlist_books,
                           reviews=reviews, downloads=downloads)

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    user = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if user is None:
        abort(404)
    if user["role"] == "admin":
        flash("Admin accounts cannot be deleted.", "error")
    else:
        execute_db("DELETE FROM users WHERE id = ?", (user_id,))
        log_admin_activity(get_current_user()["id"], "delete_user", f"Deleted user \"{user['username']}\"")
        flash(f"User '{user['username']}' deleted.", "success")
    return redirect(url_for("admin_users"))

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404

@app.errorhandler(413)
def file_too_large(error):
    flash("File is too large. Maximum size is 50 MB.", "error")
    return redirect(request.referrer or url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Start the app
# ---------------------------------------------------------------------------
init_db()

if __name__ == "__main__":
    app.run(debug=True)