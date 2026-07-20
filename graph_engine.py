import json
from pathlib import Path
from typing import Dict

DATA_DIR = Path("data/graphs")
USER_DIR = Path("data/users")

def load_graph(graph_id: str) -> Dict:
    p = DATA_DIR / f"{graph_id}.json"
    return json.loads(p.read_text()) if p.exists() else {"id": graph_id, "name": "", "topics": {}}

def save_graph(graph_id: str, graph: Dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{graph_id}.json").write_text(json.dumps(graph, indent=2))

def load_user(user_id: str = "default") -> Dict:
    p = USER_DIR / f"{user_id}.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"user_id": user_id, "graphs": {}, "daily_xp": {}, "total_xp": 0}

def save_user(user_id: str, user: Dict):
    USER_DIR.mkdir(parents=True, exist_ok=True)
    (USER_DIR / f"{user_id}.json").write_text(json.dumps(user, indent=2))

def get_topic_status(graph: Dict, user_graph: Dict, topic_id: str) -> str:
    ug = user_graph.get(topic_id, {})
    if ug.get("status") == "learned":
        return "learned"
    prereqs = graph.get("topics", {}).get(topic_id, {}).get("prerequisites", [])
    for pr in prereqs:
        if user_graph.get(pr, {}).get("status") != "learned":
            return "not_ready"
    return "ready"

def update_all_statuses(graph: Dict, user_graph: Dict):
    """Fixed-point iteration to resolve readiness states."""
    changed = True
    while changed:
        changed = False
        for tid in graph.get("topics", {}):
            current = user_graph.get(tid, {}).get("status", "not_ready")
            if current == "learned":
                continue
            computed = get_topic_status(graph, user_graph, tid)
            if computed != current:
                user_graph.setdefault(tid, {})["status"] = computed
                changed = True
