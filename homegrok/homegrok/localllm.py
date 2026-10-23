"""Backup brain: an open-source model (Llama 3.2 3B) running on the Mac's GPU through Ollama.

HomeGrok uses it when your Claude plan's limit is used up, or when you pick "Local model only".
It is much smaller than Claude, so answers are simpler, but it costs nothing and works offline.
"""
import json
import urllib.error
import urllib.request

OLLAMA = "http://127.0.0.1:11434"
MODEL = "llama3.2:3b"
SYSTEM = ("You are HomeGrok's backup brain, a small model running on the user's Mac while their Claude plan is "
          "used up. Be helpful, concise and honest; say so when you aren't sure, and never make up facts or links.")


def available():
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as resp:
            return any(m.get("name", "").startswith(MODEL) for m in json.load(resp).get("models", []))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def chat(message, history=(), on_text=None, timeout=300):
    """Stream an answer from the local model. Returns the full text."""
    messages = [{"role": "system", "content": SYSTEM}]
    messages += [{"role": "assistant" if t["role"] == "assistant" else "user", "content": t["text"]} for t in history[-6:]]
    messages.append({"role": "user", "content": message})
    request = urllib.request.Request(f"{OLLAMA}/api/chat", json.dumps(
        {"model": MODEL, "messages": messages, "stream": True}).encode(), {"Content-Type": "application/json"})
    parts = []
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        for line in resp:
            if not line.strip():
                continue
            piece = json.loads(line).get("message", {}).get("content", "")
            if piece:
                parts.append(piece)
                if on_text:
                    on_text(piece)
    return "".join(parts)
