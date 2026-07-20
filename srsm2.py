from datetime import datetime, timedelta
from typing import Dict

def init_sr_data() -> Dict:
    return {
        "ease_factor": 2.5,
        "interval": 0,
        "repetitions": 0,
        "next_review": None,
        "last_reviewed": None
    }

def is_due(sr_data: Dict) -> bool:
    nxt = sr_data.get("next_review")
    if nxt is None:
        return False
    return datetime.fromisoformat(nxt) <= datetime.now()

def schedule_review(quality: int, ease: float, interval: int, repetitions: int) -> Dict:
    """
    Classic SuperMemo-2 (Anki) algorithm.
    quality: 0=Blackout, 1=Hard, 3=Hesitant, 5=Perfect
    """
    if quality < 3:
        repetitions = 0
        interval = 1
        ease = max(1.3, ease - 0.2)
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = int(interval * ease)
        repetitions += 1
        ease += 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        ease = max(1.3, ease)

    next_review = (datetime.now() + timedelta(days=interval)).isoformat()
    return {
        "ease_factor": round(ease, 2),
        "interval": interval,
        "repetitions": repetitions,
        "next_review": next_review,
        "last_reviewed": datetime.now().isoformat()
    }
