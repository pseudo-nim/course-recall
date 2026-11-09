"""JSON-file backed storage for Course Recall."""
import json
import os
import threading
import uuid

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STORE_PATH = os.path.join(DATA_DIR, "store.json")

_lock = threading.Lock()


def _default_store():
    return {"courses": {}, "settings": {"ai_enabled": False, "api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}}


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load():
    with _lock:
        if not os.path.exists(STORE_PATH):
            return _default_store()
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    store = _default_store()
    store.update(data)
    store["settings"].update(data.get("settings", {}))
    return store


def save(store):
    with _lock:
        _ensure_dir()
        tmp = STORE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
        os.replace(tmp, STORE_PATH)


def new_id():
    return uuid.uuid4().hex[:12]


def get_course(store, course_id):
    return store["courses"].get(course_id)


def create_course(name, description=""):
    store = load()
    course_id = new_id()
    store["courses"][course_id] = {
        "id": course_id,
        "name": name,
        "description": description,
        "created_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "notes": [],
        "flashcards": [],
        "quiz": [],
        "attempts": [],
    }
    save(store)
    return store["courses"][course_id]


def update_course(course):
    store = load()
    store["courses"][course["id"]] = course
    save(store)


def delete_course(course_id):
    store = load()
    store["courses"].pop(course_id, None)
    save(store)


def get_settings():
    return load()["settings"]


def save_settings(settings):
    store = load()
    store["settings"] = settings
    save(store)
