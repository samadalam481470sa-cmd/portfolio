"""The saved conversation (workspace/chat.jsonl). It is shown whenever the page opens, and
what you say in it feeds HomeGrok's memory and its background tasks."""
import fcntl
import json
import time


class ChatLog:
    def __init__(self, ws):
        self.path = ws.root / "chat.jsonl"
        self.lock_path = ws.root / "chat.lock"

    def append(self, role, text, **meta):
        entry = {"time": time.time(), "role": role, "text": text, **meta}
        with open(self.lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return entry

    def recent(self, n=60):
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(line) for line in lines if line.strip()]

    def user_messages(self, n=40):
        """What you have told HomeGrok yourself, oldest first."""
        return [e["text"][:600] for e in self.recent(400) if e["role"] == "user"][-n:]
