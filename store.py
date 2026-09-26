"""JSON-file storage for the editable site content and dashboard users.

Live data lives in ``data/`` (never served, never overwritten by deploys).
On first run it is created from ``seed_content.json`` and a default user.
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import threading
import uuid

from werkzeug.security import check_password_hash, generate_password_hash

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
CONTENT_FILE = os.path.join(DATA_DIR, "content.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SECRET_FILE = os.path.join(DATA_DIR, "secret_key")
SEED_FILE = os.path.join(HERE, "seed_content.json")

DEFAULT_USER = ("harith", "1234")

_lock = threading.RLock()
_cache: dict[str, tuple[float, object]] = {}


def _read_json(path: str):
    mtime = os.path.getmtime(path)
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return copy.deepcopy(cached[1])
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    _cache[path] = (mtime, value)
    return copy.deepcopy(value)


def _write_json(path: str, value) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = "%s.%s.tmp" % (path, uuid.uuid4().hex)
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    os.replace(temp, path)
    _cache.pop(path, None)


def _seed() -> dict:
    with open(SEED_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def ensure_data() -> None:
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(CONTENT_FILE):
            _write_json(CONTENT_FILE, _seed())
        if not os.path.exists(USERS_FILE):
            name, password = DEFAULT_USER
            _write_json(USERS_FILE, [{"username": name, "password_hash": generate_password_hash(password)}])


def secret_key() -> str:
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    ensure_data()
    if not os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_hex(32))
    with open(SECRET_FILE, encoding="utf-8") as handle:
        return handle.read().strip()


def load_content() -> dict:
    ensure_data()
    content = _read_json(CONTENT_FILE)
    # Fill keys added to the seed after this data file was created.
    seed = _seed()
    for key, value in seed.items():
        content.setdefault(key, value)
    for group in ("settings", "sections", "trip"):
        for key, value in seed[group].items():
            if isinstance(value, dict):
                for sub, subvalue in value.items():
                    content[group].setdefault(key, {}).setdefault(sub, subvalue)
            else:
                content[group].setdefault(key, value)
    return content


def save_content(content: dict) -> None:
    with _lock:
        _write_json(CONTENT_FILE, content)


def reset_content() -> None:
    save_content(_seed())


def new_id() -> str:
    return uuid.uuid4().hex[:10]


# ----- users -----------------------------------------------------------------

def load_users() -> list[dict]:
    ensure_data()
    return _read_json(USERS_FILE)


def save_users(users: list[dict]) -> None:
    with _lock:
        _write_json(USERS_FILE, users)


def verify_user(username: str, password: str) -> bool:
    for user in load_users():
        if user["username"] == username:
            return check_password_hash(user["password_hash"], password)
    return False


def set_password(username: str, password: str) -> None:
    users = load_users()
    for user in users:
        if user["username"] == username:
            user["password_hash"] = generate_password_hash(password)
            break
    else:
        users.append({"username": username, "password_hash": generate_password_hash(password)})
    save_users(users)


def delete_user(username: str) -> None:
    save_users([user for user in load_users() if user["username"] != username])
