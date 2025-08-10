import json
import os
from datetime import datetime

USERS_FILE = "users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = f.read().strip()
            if not data:
                return {}
            return json.loads(data)
    except Exception:
        return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def add_user(user_id, first_name, games=None):
    users = load_users()
    user_id = str(user_id)
    if user_id not in users:
        users[user_id] = {
            "first_name": first_name,
            "games": games or [],
            "registered_at": datetime.now().isoformat(),
            "wallet": 0,
            "points": 0
        }
    else:
        if games:
            users[user_id]["games"] = list(set(users[user_id]["games"]) | set(games))
    save_users(users)

def set_user_games(user_id, games):
    users = load_users()
    user_id = str(user_id)
    if user_id in users:
        users[user_id]["games"] = list(set(games))
        save_users(users)

def get_user(user_id):
    users = load_users()
    return users.get(str(user_id), None)

def get_all_users():
    return load_users()

def update_wallet(user_id, amount):
    users = load_users()
    user_id = str(user_id)
    if user_id in users:
        users[user_id]["wallet"] = users[user_id].get("wallet", 0) + amount
        save_users(users)
        return users[user_id]["wallet"]
    return None

def set_wallet(user_id, amount):
    users = load_users()
    user_id = str(user_id)
    if user_id in users:
        users[user_id]["wallet"] = amount
        save_users(users)
        return users[user_id]["wallet"]
    return None

def update_points(user_id, points):
    users = load_users()
    user_id = str(user_id)
    if user_id in users:
        users[user_id]["points"] = users[user_id].get("points", 0) + points
        save_users(users)
        return users[user_id]["points"]
    return None

def set_points(user_id, points):
    users = load_users()
    user_id = str(user_id)
    if user_id in users:
        users[user_id]["points"] = points
        save_users(users)
        return users[user_id]["points"]
    return None
