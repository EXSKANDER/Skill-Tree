"""Spaced repetition: Anki's open-source SM-2 variant, at day granularity.

This is the review-card algorithm of Anki 2.1's v2 scheduler with default
deck options, applied to whole topic nodes instead of flashcards:

    starting ease            2.50
    minimum ease             1.30
    graduating interval      1 day
    hard multiplier          1.20
    easy bonus               1.30
    interval modifier        1.00
    maximum interval         36500 days
    lapse (Again)            ease -0.20, interval reset to 1 day
    Hard                     ease -0.15, interval = ivl * 1.2
    Good                     interval = (ivl + delay/2) * ease
    Easy                     ease +0.15, interval = (ivl + delay) * ease * 1.3

where delay = days the review is overdue. As in Anki, each answer's interval
is at least one day longer than the previous answer's would have been
(hard >= ivl+1, good >= hard+1, easy >= good+1), so gaps always widen.

Deliberate deviations from Anki, documented:
  * sub-day learning steps (1m/10m) are collapsed -- completing a lesson
    graduates the node straight to a 1-day interval;
  * no random interval fuzz -- scheduling stays deterministic and diffable.
"""

import datetime
import math

START_EASE = 2.5
MIN_EASE = 1.3
HARD_FACTOR = 1.2
EASY_BONUS = 1.3
GRADUATING_IVL = 1
MAX_IVL = 36500
LAPSE_MULT = 0.0
LAPSE_MIN_IVL = 1

GRADES = ("again", "hard", "good", "easy")


def _round(x):
    return int(math.floor(x + 0.5))


def init_srs(today):
    """Called when a node's lesson is completed (the node graduates)."""
    return {
        "ease": START_EASE,
        "ivl": GRADUATING_IVL,
        "due": (today + datetime.timedelta(days=GRADUATING_IVL)).isoformat(),
        "reps": 0,
        "lapses": 0,
        "consec_again": 0,
        "last_problem": None,
    }


def review(srs, grade, today):
    """Apply one review answer in place and return srs."""
    if grade not in GRADES:
        raise ValueError("grade must be one of %s" % (GRADES,))
    due = datetime.date.fromisoformat(srs["due"])
    delay = max(0, (today - due).days)
    ease = srs["ease"]
    ivl = srs["ivl"]

    if grade == "again":
        ease = max(MIN_EASE, ease - 0.20)
        ivl = max(LAPSE_MIN_IVL, _round(ivl * LAPSE_MULT))
        srs["lapses"] += 1
        srs["consec_again"] = srs.get("consec_again", 0) + 1
    else:
        hard = max(_round(ivl * HARD_FACTOR), ivl + 1)
        good = max(_round((ivl + delay // 2) * ease), hard + 1)
        easy = max(_round((ivl + delay) * ease * EASY_BONUS), good + 1)
        if grade == "hard":
            ease = max(MIN_EASE, ease - 0.15)
            ivl = hard
        elif grade == "good":
            ivl = good
        else:
            ease += 0.15
            ivl = easy
        srs["consec_again"] = 0

    ivl = min(ivl, MAX_IVL)
    srs["ease"] = round(ease, 2)
    srs["ivl"] = ivl
    srs["due"] = (today + datetime.timedelta(days=ivl)).isoformat()
    srs["reps"] = srs.get("reps", 0) + 1
    return srs
