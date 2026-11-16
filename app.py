from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_login import login_required as require_login
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
app = Flask(__name__)

app.config["SECRET_KEY"] = "skillmap-secret-key-change-later"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
class User(UserMixin):
    def __init__(self, user_id, username, password_hash,
                 email=None, role="student", is_active=1):
        self.id = user_id
        self.username = username
        self.password_hash = password_hash
        self.email = email
        self.role = role
        self._is_active = bool(is_active)
    @property
    def is_active(self):
        return self._is_active


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()

    conn.close()

    if user:
        return User(
            user["id"],
            user["username"],
            user["password_hash"],
            user["email"],
            user["role"],
            user["is_active"]
        )

    return None

# Database connection
def get_db_connection():
    conn = sqlite3.connect("skillmap.db")
    conn.row_factory = sqlite3.Row
    return conn


# Record an activity
def log_activity(conn, item_type, item_id, item_name, action,
                 old_progress=None, new_progress=None):
    conn.execute(
        """INSERT INTO activity_log
           (item_type, item_id, item_name, action,
            old_progress, new_progress)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (item_type, item_id, item_name, action,
         old_progress, new_progress)
    )


# Create database tables
def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            progress INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            target_date TEXT NOT NULL,
            progress INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    # Safely add new columns to the users table
    user_columns = [
        column["name"]
        for column in conn.execute("PRAGMA table_info(users)").fetchall()
    ]

    if "email" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")

    if "role" not in user_columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'"
        )

    if "is_active" not in user_columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
        )

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            old_progress INTEGER,
            new_progress INTEGER,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(activity_log)"
        ).fetchall()
    ]

    if "item_name" not in columns:
        conn.execute(
            "ALTER TABLE activity_log ADD COLUMN item_name TEXT"
        )
    # Assign existing records to the Admin account
    admin = conn.execute(
        "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
    ).fetchone()

    if admin:
        admin_id = admin["id"]

        for table in ("skills", "goals", "activity_log"):
            columns = [
                column["name"]
                for column in conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            ]

            if "user_id" not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"
                )

            conn.execute(
                f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL",
                (admin_id,)
            )
    conn.commit()
    conn.close()
# Sign Up
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("Please fill in all fields.")
            return redirect(url_for("signup"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return redirect(url_for("signup"))

        if password != confirm_password:
            flash("Passwords do not match.")
            return redirect(url_for("signup"))

        conn = get_db_connection()

        existing_user = conn.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email)
        ).fetchone()

        if existing_user:
            conn.close()
            flash("Username or email already exists.")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password)

        conn.execute(
            """
            INSERT INTO users (username, email, password_hash, role, is_active)
            VALUES (?, ?, ?, 'student', 1)
            """,
            (username, email, password_hash)
        )

        conn.commit()
        conn.close()

        flash("Account created successfully. Please log in.")
        return redirect(url_for("login"))

    return render_template("signup.html")
# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()

        user = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (username, username.lower())
        ).fetchone()

        conn.close()

        if user and user["is_active"] and check_password_hash(
            user["password_hash"], password
        ):
            login_user(
                User(
                    user["id"],
                    user["username"],
                    user["password_hash"],
                    user["email"],
                    user["role"],
                    user["is_active"]
                )
            )
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.")

    return render_template("login.html")
# Logout
@app.route("/logout")
@require_login
def logout():
    logout_user()
    return redirect(url_for("login"))

    # Dashboard
@app.route("/")
@require_login
def dashboard():
    conn = get_db_connection()

    total_skills = conn.execute(
        "SELECT COUNT(*) FROM skills WHERE user_id = ?",
        (current_user.id,)
    ).fetchone()[0]

    completed_skills = conn.execute(
        "SELECT COUNT(*) FROM skills WHERE user_id = ? AND progress = 100",
        (current_user.id,)
    ).fetchone()[0]

    overall_progress = conn.execute(
        "SELECT AVG(progress) FROM skills WHERE user_id = ?",
        (current_user.id,)
    ).fetchone()[0] or 0

    recent_skills = conn.execute(
        "SELECT * FROM skills WHERE user_id = ? ORDER BY id DESC LIMIT 4",
        (current_user.id,)
    ).fetchall()

    active_goals = conn.execute(
        "SELECT COUNT(*) FROM goals WHERE user_id = ? AND progress < 100",
        (current_user.id,)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        total_skills=total_skills,
        completed_skills=completed_skills,
        overall_progress=round(overall_progress),
        recent_skills=recent_skills,
        active_goals=active_goals
    )
# My Skills page
@app.route("/skills")
@require_login
def skills():
    conn = get_db_connection()

    all_skills = conn.execute(
        "SELECT * FROM skills WHERE user_id = ? ORDER BY id DESC",
        (current_user.id,)
    ).fetchall()

    conn.close()

    return render_template("skills.html", skills=all_skills)
# Add a skill
@app.route("/add_skill", methods=["POST"])
@require_login
def add_skill():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "")

    try:
        progress = int(request.form.get("progress", 0))
    except ValueError:
        return "Invalid progress value", 400

    if not name or not 0 <= progress <= 100:
        return "Invalid skill details", 400

    conn = get_db_connection()

    cursor = conn.execute(
        "INSERT INTO skills (name, category, progress) VALUES (?, ?, ?)",
        (name, category, progress)
    )

    log_activity(
        conn, "skill", cursor.lastrowid, name, "added",
                 None, progress
    )

    conn.commit()
    conn.close()

    return redirect(url_for("skills"))


# Edit a skill
@app.route("/edit_skill/<int:skill_id>", methods=["GET", "POST"])
@require_login
def edit_skill(skill_id):
    conn = get_db_connection()

    skill = conn.execute(
        "SELECT * FROM skills WHERE id = ?", (skill_id,)
    ).fetchone()

    if skill is None:
        conn.close()
        return "Skill not found", 404

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "")

        try:
            progress = int(request.form.get("progress", 0))
        except ValueError:
            conn.close()
            return "Invalid progress value", 400

        if not name or not 0 <= progress <= 100:
            conn.close()
            return "Invalid skill details", 400

        old_progress = skill["progress"]

        conn.execute(
            """UPDATE skills
               SET name = ?, category = ?, progress = ?
               WHERE id = ?""",
            (name, category, progress, skill_id)
        )

        if progress != old_progress:
            log_activity(
                conn, "skill", skill_id, name, "progress_updated",
                old_progress, progress
            )

        conn.commit()
        conn.close()

        return redirect(url_for("skills"))

    conn.close()

    return render_template("edit_skill.html", skill=skill)


# Delete a skill
@app.route("/delete_skill/<int:skill_id>", methods=["POST"])
@require_login
def delete_skill(skill_id):
    conn = get_db_connection()

    skill = conn.execute(
        "SELECT * FROM skills WHERE id = ?", (skill_id,)
    ).fetchone()

    if skill:
        log_activity(
            conn, "skill", skill_id, skill["name"], "deleted",
            skill["progress"], None
        )

        conn.execute(
            "DELETE FROM skills WHERE id = ?", (skill_id,)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("skills"))


# Learning Goals page
@app.route("/goals")
@require_login
def goals():
    conn = get_db_connection()

    goals = conn.execute(
        "SELECT * FROM goals ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template("goals.html", goals=goals)


# Add a goal
@app.route("/add_goal", methods=["POST"])
@require_login
def add_goal():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    target_date = request.form.get("target_date", "")

    try:
        progress = int(request.form.get("progress", 0))
    except ValueError:
        return "Invalid progress value", 400

    if not title or not target_date or not 0 <= progress <= 100:
        return "Invalid goal details", 400

    conn = get_db_connection()

    cursor = conn.execute(
        """INSERT INTO goals
           (title, description, target_date, progress)
           VALUES (?, ?, ?, ?)""",
        (title, description, target_date, progress)
    )

    action = "completed" if progress == 100 else "added"

    log_activity(
        conn, "goal", cursor.lastrowid, title, action, None, progress
    )

    conn.commit()
    conn.close()

    return redirect(url_for("goals"))


# Edit a goal
@app.route("/edit_goal/<int:goal_id>", methods=["GET", "POST"])
@require_login
def edit_goal(goal_id):
    conn = get_db_connection()

    goal = conn.execute(
        "SELECT * FROM goals WHERE id = ?", (goal_id,)
    ).fetchone()

    if goal is None:
        conn.close()
        return "Goal not found", 404

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        target_date = request.form.get("target_date", "")

        try:
            progress = int(request.form.get("progress", 0))
        except ValueError:
            conn.close()
            return "Invalid progress value", 400

        if not title or not target_date or not 0 <= progress <= 100:
            conn.close()
            return "Invalid goal details", 400

        old_progress = goal["progress"]

        conn.execute(
            """UPDATE goals
               SET title = ?, description = ?,
                   target_date = ?, progress = ?
               WHERE id = ?""",
            (title, description, target_date, progress, goal_id)
        )

        if progress != old_progress:
            action = (
                "completed"
                if progress == 100 and old_progress < 100
                else "progress_updated"
            )

            log_activity(
                conn, "goal", goal_id, title, action,
                old_progress, progress
            )

        conn.commit()
        conn.close()

        return redirect(url_for("goals"))

    conn.close()

    return render_template("edit_goal.html", goal=goal)


# Delete a goal
@app.route("/delete_goal/<int:goal_id>", methods=["POST"])
@require_login
def delete_goal(goal_id):
    conn = get_db_connection()

    goal = conn.execute(
        "SELECT * FROM goals WHERE id = ?", (goal_id,)
    ).fetchone()

    if goal:
        log_activity(
            conn, "goal", goal_id, goal["title"], "deleted",
            goal["progress"], None
        )

        conn.execute(
            "DELETE FROM goals WHERE id = ?", (goal_id,)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("goals"))


# Analytics page
@app.route("/analytics")
@require_login
def analytics():
    conn = get_db_connection()

    skills = conn.execute(
        "SELECT name, progress FROM skills ORDER BY id"
    ).fetchall()

    total_skills = len(skills)

    completed_skills = sum(
        1 for skill in skills if skill["progress"] == 100
    )

    average_progress = round(
        sum(skill["progress"] for skill in skills) / total_skills
    ) if total_skills else 0

    goals = conn.execute(
        "SELECT COUNT(*) FROM goals"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "analytics.html",
        skills=skills,
        total_skills=total_skills,
        completed_skills=completed_skills,
        average_progress=average_progress,
        total_goals=goals
    )


# Weekly Report - Last 7 Days
@app.route("/weekly-report")
@require_login
def weekly_report():
    conn = get_db_connection()

    activities = conn.execute("""
        SELECT *
        FROM activity_log
        WHERE created_at >= datetime('now', 'localtime', '-6 days')
        ORDER BY created_at DESC
    """).fetchall()

    skills_added = sum(
        1 for a in activities
        if a["item_type"] == "skill" and a["action"] == "added"
    )

    skills_updated = sum(
        1 for a in activities
        if a["item_type"] == "skill"
        and a["action"] == "progress_updated"
    )

    goals_added = sum(
        1 for a in activities
        if a["item_type"] == "goal" and a["action"] == "added"
    )

    goals_completed = sum(
        1 for a in activities
        if a["item_type"] == "goal" and a["action"] == "completed"
    )

    goals_updated = sum(
        1 for a in activities
        if a["item_type"] == "goal"
        and a["action"] == "progress_updated"
    )

    upcoming_goals = conn.execute("""
        SELECT *
        FROM goals
        WHERE progress < 100
          AND target_date >= date('now', 'localtime')
          AND target_date <= date('now', 'localtime', '+7 days')
        ORDER BY target_date
    """).fetchall()

    daily_activity = conn.execute("""
        SELECT date(created_at) AS activity_date,
               COUNT(*) AS activity_count
        FROM activity_log
        WHERE created_at >= datetime('now', 'localtime', '-6 days')
        GROUP BY date(created_at)
        ORDER BY activity_date
    """).fetchall()

    conn.close()

    return render_template(
        "weekly_report.html",
        activities=activities,
        skills_added=skills_added,
        skills_updated=skills_updated,
        goals_added=goals_added,
        goals_completed=goals_completed,
        goals_updated=goals_updated,
        upcoming_goals=upcoming_goals,
        daily_activity=daily_activity
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True)