"""XP: 1 xp represents ~1 minute of fully-focused, productive work.

Awards (following The Math Academy Way's gamification notes):
  * lesson problems  -- a node worth `minutes` xp pays out per problem
                        (minutes // n_problems each, remainder on completion)
  * reviews          -- graded: easy = base+1 (perfect bonus), good = base,
                        hard = half, again = 0
  * quiz bonus       -- +25% for a perfect quiz (all items good/easy)
  * manual           -- `st xp add` for corrections and blow-off penalties

The ledger (state/xp.tsv) is append-only; totals are always derived from it.
"""

import datetime
import math

from . import store


def problem_share(minutes, n_problems):
    """(xp per problem, remainder paid on lesson completion)."""
    if n_problems <= 0:
        return 0, max(0, minutes)
    share = max(1, minutes // n_problems) if minutes else 0
    paid = min(minutes, share * n_problems)
    return share, minutes - paid


def review_award(cfg, grade):
    base = int(cfg.get("review_minutes", 2))
    return {
        "easy": base + 1,
        "good": base,
        "hard": max(1, base // 2),
        "again": 0,
    }[grade]


def quiz_bonus(item_xp_total):
    return max(1, int(math.floor(item_xp_total * 0.25 + 0.5)))


def award(root, graph, node, event, amount, note=""):
    if amount == 0:
        return
    store.append_ledger(root, graph, node, event, amount, note)


def summary(root, cfg, today):
    entries = store.read_ledger(root)
    by_day = {}
    total = 0
    for e in entries:
        day = e["at"][:10]
        by_day[day] = by_day.get(day, 0) + e["xp"]
        total += e["xp"]
    goal = int(cfg.get("daily_goal", 30))
    streak = 0
    day = today
    # today counts toward the streak only once the goal is met
    if by_day.get(day.isoformat(), 0) >= goal:
        streak += 1
    day -= datetime.timedelta(days=1)
    while by_day.get(day.isoformat(), 0) >= goal:
        streak += 1
        day -= datetime.timedelta(days=1)
    last7 = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        last7.append((d.isoformat(), by_day.get(d.isoformat(), 0)))
    return {
        "total": total,
        "today": by_day.get(today.isoformat(), 0),
        "goal": goal,
        "streak": streak,
        "last7": last7,
    }
