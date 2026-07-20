from datetime import datetime

def award_xp(user: dict, amount: int):
    today = datetime.now().strftime("%Y-%m-%d")
    user.setdefault("daily_xp", {})
    user["daily_xp"].setdefault(today, 0)
    user["daily_xp"][today] += amount
    user["total_xp"] = user.get("total_xp", 0) + amount

def get_today_xp(user: dict) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    return user.get("daily_xp", {}).get(today, 0)
