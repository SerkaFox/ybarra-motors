from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from pathlib import Path

from copy import deepcopy

from .defaults import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    PAGE_DEFINITIONS,
    SITE_SETTINGS_DEFAULT,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "cms_data"
DB_PATH = DATA_DIR / "site.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: str | None = None) -> str:
    real_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        real_salt.encode("utf-8"),
        120000,
    ).hex()
    return f"{real_salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, _sep, digest = stored.partition("$")
    if not salt or not digest:
        return False
    check = hash_password(password, salt).partition("$")[2]
    return secrets.compare_digest(check, digest)


def initialize_database() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pages (
                slug TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                path TEXT NOT NULL,
                url TEXT NOT NULL,
                content_json TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        user_exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (DEFAULT_ADMIN_USERNAME,),
        ).fetchone()
        if not user_exists:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (
                    DEFAULT_ADMIN_USERNAME,
                    hash_password(DEFAULT_ADMIN_PASSWORD),
                ),
            )

        for slug, meta in PAGE_DEFINITIONS.items():
            row = conn.execute("SELECT content_json FROM pages WHERE slug = ?", (slug,)).fetchone()
            if not row:
                default_content = SITE_SETTINGS_DEFAULT if slug == "site-settings" else {}
                conn.execute(
                    """
                    INSERT INTO pages (slug, kind, title, path, url, content_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        meta["kind"],
                        meta["label"],
                        meta["path"],
                        meta["url"],
                        json.dumps(default_content, ensure_ascii=False),
                    ),
                )
            elif slug == "site-settings":
                current_content = json.loads(row["content_json"])
                if not current_content:
                    conn.execute(
                        "UPDATE pages SET content_json = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
                        (json.dumps(SITE_SETTINGS_DEFAULT, ensure_ascii=False), slug),
                    )


def list_pages() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT slug, kind, title, path, url, updated_at FROM pages ORDER BY slug"
        ).fetchall()


def get_page(slug: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM pages WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        page = dict(row)
        page["content"] = json.loads(page.pop("content_json"))
        return page


def get_site_settings() -> dict:
    page = get_page("site-settings")
    if not page or not page["content"]:
        return deepcopy(SITE_SETTINGS_DEFAULT)

    merged = deepcopy(SITE_SETTINGS_DEFAULT)
    deep_merge(merged, page["content"])
    return merged


def deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def save_page(slug: str, title: str, content: dict) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE pages
            SET title = ?, content_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE slug = ?
            """,
            (title, json.dumps(content, ensure_ascii=False), slug),
        )


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
        conn.execute(
            "INSERT INTO sessions (token, username) VALUES (?, ?)",
            (token, username),
        )
    return token


def delete_session(token: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_session_user(token: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username FROM sessions WHERE token = ?",
            (token,),
        ).fetchone()
        return row["username"] if row else None


def authenticate(username: str, password: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return False
    return verify_password(password, row["password_hash"])


def update_password(username: str, new_password: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
            WHERE username = ?
            """,
            (hash_password(new_password), username),
        )
