from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, Response, stream_with_context
import uuid
import time
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

import psycopg2
import psycopg2.extras
import psycopg2.errors

from engine import process_user_query
from config import get_api_key, get_db_connection

# ---------------------
# App & DB init
# ---------------------
app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secret_key")

MODEL_NAME = "gpt-5"

# ---------------------
# DB helper wrappers
# ---------------------
def fetchone_dict(conn, query, params=()):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query, params)
    row = cur.fetchone()
    cur.close()
    return row

def fetchall_dict(conn, query, params=()):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows

def execute(conn, query, params=(), commit=False, returning=False):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query, params)
    result = None
    if returning:
        result = cur.fetchone()
    if commit:
        conn.commit()
    cur.close()
    return result


# ---------------------
# System prompt
# ---------------------
SYSTEM_PROMPT = {
    "role": "system",
    "content": """You are BioBot 🤖, an expert assistant specialized in lab automation, particularly with liquid handling robots.
Your tasks:
- A chat history is provided to help you recall previous interactions, but **do not process the entire history as new instructions**; use it only if you need to reference something the user said before. To answer, focus primarily on the **latest user message**.
- If the user asks for code for protocols, generate clean, error-free Python code for operating lab robots.
- Ask for more informations if you assume that there are not enough informations in order to generate the code. You are specialized, you know what informations to ask.
- Do not answer queries that have nohing to do with your specialization which is lab automation, liquid handlers and other related fields. Decline kindly."""
}


# ---------------------
# Auth routes
# ---------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        api_key = request.form.get("api_key", "").strip() or get_api_key()
        role = request.form.get("role", "")
        country = request.form.get("country", "")

        conn = None
        try:
            conn = get_db_connection()
            execute(conn,
                """
                INSERT INTO users (first_name, last_name, email, password, api_key, role, country, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (first_name, last_name, email, password, api_key, role, country, datetime.now().isoformat()),
                commit=True
            )
            flash("Inscription réussie ! Connectez-vous.", "success")
            return redirect("/login")
        except psycopg2.errors.UniqueViolation:
            if conn:
                conn.rollback()
            flash("Email déjà utilisé.", "error")
            return redirect("/register")
        except Exception as e:
            if conn:
                conn.rollback()
            print("Register error:", e)
            flash("Erreur interne lors de l'inscription.", "error")
            return redirect("/register")
        finally:
            if conn:
                conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "HEAD":
        return "", 200
    
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = None
        try:
            conn = get_db_connection()
            user = fetchone_dict(conn, "SELECT * FROM users WHERE email = %s", (email,))
        finally:
            if conn:
                conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["id"]
            return redirect("/")
        else:
            flash("Email ou mot de passe incorrect !", "error")
            return redirect("/login")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for("login"))


# ---------------------
# Main routes
# ---------------------
@app.route("/")
def index():
    user_id = session.get("user")
    if not user_id:
        return redirect("/login")
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        session.pop("user", None)
        return redirect("/login")

    conn = None
    try:
        conn = get_db_connection()
        user = fetchone_dict(conn, "SELECT * FROM users WHERE id = %s", (user_id,))
    finally:
        if conn:
            conn.close()

    if not user:
        session.pop("user", None)
        return redirect("/login")

    return render_template("index.html", user=user)


@app.route("/chat", methods=["POST"])
def create_chat():
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    chat_id = str(uuid.uuid4())
    title = "New chat"

    conn = None
    try:
        conn = get_db_connection()
        execute(conn,
            "INSERT INTO chat_names (chat_id, user_id, name) VALUES (%s, %s, %s)",
            (chat_id, user_id, title),
            commit=True
        )

        system_message = SYSTEM_PROMPT["content"]
        execute(conn,
            "INSERT INTO chat_history (user_id, chat_id, role, content) VALUES (%s, %s, %s, %s)",
            (user_id, chat_id, "system", system_message),
            commit=True
        )

        intro_message = "Hello, I'm Biobot 🤖 — your assistant specialized in lab automation..."
        execute(conn,
            "INSERT INTO chat_history (user_id, chat_id, role, content) VALUES (%s, %s, %s, %s)",
            (user_id, chat_id, "assistant", intro_message),
            commit=True
        )
    except Exception as e:
        if conn:
            conn.rollback()
        print("create_chat error:", e)
        return jsonify({"error": "Database error"}), 500
    finally:
        if conn:
            conn.close()

    return jsonify({"chat_id": chat_id}), 201


@app.route("/chat/<chat_id>", methods=["POST"])
def chat(chat_id):
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    data = request.get_json()
    user_message = data.get("message")
    if not user_message:
        return jsonify({"error": "Message required"}), 400

    conn = None
    try:
        conn = get_db_connection()

        # verify chat belongs to user
        chat_exists = fetchone_dict(conn,
            "SELECT 1 FROM chat_names WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )

        # insert user message
        execute(conn,
            "INSERT INTO chat_history (user_id, chat_id, role, content, created_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, chat_id, "user", user_message, datetime.now().isoformat()),
            commit=True
        )

        # fetch full history
        rows = fetchall_dict(conn,
            "SELECT role, content FROM chat_history WHERE user_id = %s AND chat_id = %s ORDER BY created_at",
            (user_id, chat_id)
        )

        user = fetchone_dict(conn, "SELECT api_key FROM users WHERE id = %s", (user_id,))
    finally:
        if conn:
            conn.close()

    user_api_key = user["api_key"] if user and user.get("api_key") else None
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    # call your engine
    bot_reply = process_user_query(user_message, messages, MODEL_NAME, api_key=user_api_key)

    # save bot response
    conn = None
    try:
        conn = get_db_connection()
        execute(conn,
            "INSERT INTO chat_history (user_id, chat_id, role, content, created_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, chat_id, "assistant", bot_reply, datetime.now().isoformat()),
            commit=True
        )

        # rename chat if still "New chat"
        title_row = fetchone_dict(conn, "SELECT name FROM chat_names WHERE chat_id = %s AND user_id = %s", (chat_id, user_id))
        if title_row and title_row.get("name") == "New chat":
            preview_words = user_message.strip().split()
            preview = " ".join(preview_words[:5])
            if len(preview_words) > 5:
                preview += "..."
            execute(conn,
                "UPDATE chat_names SET name = %s WHERE chat_id = %s AND user_id = %s",
                (preview, chat_id, user_id),
                commit=True
            )
    except Exception as e:
        if conn:
            conn.rollback()
        print("chat save error:", e)
    finally:
        if conn:
            conn.close()

    return jsonify({"reply": bot_reply})

#For streaming :
@app.route("/chat/<chat_id>/stream", methods=["POST"])
def chat_stream(chat_id):
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    data = request.get_json()
    user_message = data.get("message")
    if not user_message:
        return jsonify({"error": "Message required"}), 400

    conn = None
    try:
        conn = get_db_connection()

        # verify chat exists
        chat_exists = fetchone_dict(conn,
            "SELECT 1 FROM chat_names WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )
        if not chat_exists:
            return jsonify({"error": "Chat not found"}), 404

        # insert user message immediately
        execute(conn,
            """
            INSERT INTO chat_history (user_id, chat_id, role, content, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, chat_id, "user", user_message, datetime.now().isoformat()),
            commit=True
        )

        # ensure intro message exists (only once per chat)
        intro_exists = fetchone_dict(conn,
            "SELECT 1 FROM chat_history WHERE chat_id = %s AND role='assistant' AND content LIKE %s",
            (chat_id, "Hello, I'm Biobot%")
        )
        if not intro_exists:
            intro_message = "Hello, I'm Biobot 🤖 — your assistant specialized in lab automation..."
            execute(conn,
                """
                INSERT INTO chat_history (user_id, chat_id, role, content, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, chat_id, "assistant", intro_message, datetime.now().isoformat()),
                commit=True
            )

        # fetch full chat history for streaming
        rows = fetchall_dict(conn,
            """
            SELECT role, content
            FROM chat_history
            WHERE user_id = %s AND chat_id = %s
            ORDER BY created_at
            """,
            (user_id, chat_id)
        )

        user = fetchone_dict(conn, "SELECT api_key FROM users WHERE id = %s", (user_id,))
    finally:
        if conn:
            conn.close()

    messages = [{"role": r["role"], "content": r["content"]} for r in rows]
    user_api_key = user["api_key"] if user else None

    # ---- STREAM RESPONSE ----
    def generate():
        full_reply = ""
        is_rag = False

        from engine import RAG_STATUS_PREFIX, FAILED_CODE_MARKER
        for chunk in process_user_query(user_message, messages, MODEL_NAME, api_key=user_api_key):
            if chunk.startswith(RAG_STATUS_PREFIX):
                is_rag = True
                status_text = chunk[len(RAG_STATUS_PREFIX):]
                yield "__STATUS__:" + status_text
                continue
            full_reply += chunk
            yield chunk

        # Before saving: wrap RAG code in markdown fences so it renders
        # correctly when reloaded from chat history
        save_content = full_reply
        if is_rag and full_reply:
            if full_reply.startswith(FAILED_CODE_MARKER):
                # Failed code: extract message and code, format for storage
                failed_content = full_reply[len(FAILED_CODE_MARKER):]
                sep_parts = failed_content.split("___CODE_SEP___", 1)
                message = sep_parts[0].strip() if sep_parts else ""
                code = sep_parts[1].strip() if len(sep_parts) > 1 else ""
                save_content = message + "\n\n```python\n" + code + "\n```" if code else message
            else:
                # Successful code
                save_content = "```python\n" + full_reply + "\n```"

        # Save assistant message after streaming finishes
        conn2 = None
        try:
            conn2 = get_db_connection()
            execute(conn2,
                """
                INSERT INTO chat_history (user_id, chat_id, role, content, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, chat_id, "assistant", save_content, datetime.now().isoformat()),
                commit=True
            )

            # RENAME CHAT if still "New chat"
            title_row = fetchone_dict(conn2,
                "SELECT name FROM chat_names WHERE chat_id = %s AND user_id = %s",
                (chat_id, user_id)
            )
            if title_row and title_row.get("name") == "New chat":
                preview_words = user_message.strip().split()
                preview = " ".join(preview_words[:5])
                if len(preview_words) > 5:
                    preview += "..."
                execute(conn2,
                    "UPDATE chat_names SET name = %s WHERE chat_id = %s AND user_id = %s",
                    (preview, chat_id, user_id),
                    commit=True
                )

        finally:
            if conn2:
                conn2.close()

    return Response(stream_with_context(generate()), mimetype="text/plain")


@app.route("/chat/<chat_id>", methods=["GET"])
def get_history(chat_id):
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    conn = None
    try:
        conn = get_db_connection()
        rows = fetchall_dict(conn,
            "SELECT role, content FROM chat_history WHERE user_id = %s AND chat_id = %s ORDER BY created_at",
            (user_id, chat_id)
        )
    finally:
        if conn:
            conn.close()

    visible_messages = [{"role": r["role"], "content": r["content"]} for r in rows if r["role"] != "system"]
    return jsonify(visible_messages)


@app.route("/chat/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    conn = None
    try:
        conn = get_db_connection()
        execute(conn,
            "DELETE FROM chat_history WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id),
            commit=True
        )
        execute(conn,
            "DELETE FROM chat_names WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id),
            commit=True
        )
    except Exception as e:
        if conn:
            conn.rollback()
        print("delete_chat error:", e)
        return jsonify({"error": "Database error"}), 500
    finally:
        if conn:
            conn.close()

    return jsonify({"success": True})


@app.route("/chats", methods=["GET"])
def list_chats():
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    conn = None
    try:
        conn = get_db_connection()
        rows = fetchall_dict(conn, "SELECT chat_id, name FROM chat_names WHERE user_id = %s", (user_id,))
    finally:
        if conn:
            conn.close()

    return jsonify([{"chat_id": r["chat_id"], "name": r["name"]} for r in rows])


@app.route("/chat/<chat_id>/rename", methods=["POST"])
def rename_chat(chat_id):
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    data = request.get_json()
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Name required"}), 400

    conn = None
    try:
        conn = get_db_connection()
        execute(conn,
            "UPDATE chat_names SET name = %s WHERE chat_id = %s AND user_id = %s",
            (new_name, chat_id, user_id),
            commit=True
        )
    finally:
        if conn:
            conn.close()

    return jsonify({"success": True})


@app.route("/user/profile", methods=["GET"])
def get_user_profile():
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    conn = None
    try:
        conn = get_db_connection()
        user = fetchone_dict(conn,
            "SELECT id, first_name, last_name, email, api_key, role, country, created_at FROM users WHERE id = %s",
            (user_id,)
        )
    finally:
        if conn:
            conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify(dict(user))


@app.route("/user/profile", methods=["POST"])
def update_user_profile():
    user_id = session.get("user")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    data = request.get_json()
    first_name = data.get("first_name", "").strip()
    last_name = data.get("last_name", "").strip()
    email = data.get("email", "").strip()
    api_key = data.get("api_key", "").strip()
    country = data.get("country", "").strip()

    if not first_name or not last_name or not email:
        return jsonify({"error": "Missing required fields"}), 400

    conn = None
    try:
        conn = get_db_connection()
        execute(conn,
            """
            UPDATE users SET first_name = %s, last_name = %s, email = %s, api_key = %s, country = %s
            WHERE id = %s
            """,
            (first_name, last_name, email, api_key, country, user_id),
            commit=True
        )
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return jsonify({"error": "Email already exists"}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        print("update_user_profile error:", e)
        return jsonify({"error": "Database error"}), 500
    finally:
        if conn:
            conn.close()

    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)