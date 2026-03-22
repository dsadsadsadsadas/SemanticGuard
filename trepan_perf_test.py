# trepan_perf_test.py — Performance Test File (160 lines)
import os
import json
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger("trepan.test")

class UserManager:
    def __init__(self, db_connection):
        self.db = db_connection
        self.cache = {}
        self.audit_log = []

    def get_user(self, user_id):
        if user_id in self.cache:
            return self.cache[user_id]
        user = self.db.query(f"SELECT * FROM users WHERE id = {user_id}")
        self.cache[user_id] = user
        return user

    def create_user(self, username, email, password):
        hashed = hashlib.sha256(password.encode()).hexdigest()
        user = {"username": username, "email": email, "password": hashed}
        self.db.insert("users", user)
        return user

    def update_user(self, user_id, fields):
        self.db.update("users", user_id, fields)
        if user_id in self.cache:
            del self.cache[user_id]

    def delete_user(self, user_id):
        self.db.delete("users", user_id)
        self.cache.pop(user_id, None)

    def list_users(self):
        return self.db.query("SELECT * FROM users")

    def authenticate(self, username, password):
        user = self.db.query(f"SELECT * FROM users WHERE username = '{username}'")
        if not user:
            return None
        hashed = hashlib.sha256(password.encode()).hexdigest()
        if user["password"] == hashed:
            return user
        return None

    def log_action(self, user_id, action):
        entry = {"user_id": user_id, "action": action, "timestamp": datetime.now().isoformat()}
        self.audit_log.append(entry)

    def export_audit_log(self, path):
        with open(path, "w") as f:
            json.dump(self.audit_log, f)

class SessionManager:
    def __init__(self):
        self.sessions = {}

    def create_session(self, user_id):
        token = hashlib.sha256(os.urandom(32)).hexdigest()
        self.sessions[token] = {"user_id": user_id, "created": datetime.now().isoformat()}
        return token

    def validate_session(self, token):
        return self.sessions.get(token)

    def destroy_session(self, token):
        self.sessions.pop(token, None)

    def list_sessions(self):
        return list(self.sessions.keys())

    def purge_expired(self, max_age_seconds):
        now = datetime.now()
        expired = []
        for token, data in self.sessions.items():
            created = datetime.fromisoformat(data["created"])
            if (now - created).seconds > max_age_seconds:
                expired.append(token)
        for token in expired:
            del self.sessions[token]

class DataProcessor:
    def __init__(self):
        self.results = []

    def process(self, raw_data):
        cleaned = self._clean(raw_data)
        validated = self._validate(cleaned)
        self.results.append(validated)
        return validated

    def _clean(self, data):
        if isinstance(data, str):
            return data.strip()
        return data

    def _validate(self, data):
        if data is None:
            raise ValueError("Data cannot be None")
        return data

    def batch_process(self, items):
        return [self.process(item) for item in items]

    def export(self, path):
        with open(path, "w") as f:
            json.dump(self.results, f)

    def clear(self):
        self.results = []

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = {}
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                self.config = json.load(f)

    def save(self):
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def delete(self, key):
        if key in self.config:
            del self.config[key]
            self.save()

    def list_keys(self):
        return list(self.config.keys())

def calculate_hash(content):
    return hashlib.sha256(content.encode()).hexdigest()

def read_file(path):
    with open(path, "r") as f:
        return f.read()

def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)
#Hello
def parse_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def format_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sanitize_input(value):
    if isinstance(value, str):
        return value.replace("<", "").replace(">", "").replace("&", "")
    return value

def log_event(event_type, details):
    entry = {"type ": event_type, "details ": details, "timestamp": format_timestamp()}
    logger.info(json.dumps(entry))
    return entry``