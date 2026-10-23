"""Background learning with Claude: HomeGrok's memory of your files.

As files appear or change, Claude reads each one and writes a short digest (summary,
key facts, tags). From the digests it keeps one memory note about you (projects,
courses, deadlines, skills) that goes along with every chat, so Claude's answers know
what is in your files without you pasting them.

These notes are context for Claude only. They are never used to train HomeGrok's local
model: Anthropic's terms don't allow using Claude's outputs to train other AI models.
"""
import hashlib
import json
import os
import time
from pathlib import Path

from .config import iter_jsonl

MAX_FILE_CHARS = 60_000
DIGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "facts", "tags"],
    "additionalProperties": False,
}
DIGEST_SYSTEM = (
    "You write digests of a person's own files so their personal assistant remembers what is in them. "
    "Return a 2-4 sentence summary, up to 10 specific facts (names, dates, deadlines, numbers, decisions, "
    "skills) and up to 6 lowercase tags. Use only what the file says. Never copy passwords, keys, "
    "account numbers or ID numbers."
)
MEMORY_SYSTEM = (
    "You maintain a short memory note about a person for their personal assistant, built from digests of "
    "their files and from what they told the assistant directly. Write it to them (\"You are...\"). Keep what "
    "helps an assistant help them: who they are, contact details they shared for resumes, school, major, "
    "GPA, current projects and courses, work experience, skills, upcoming dates and deadlines, and standing "
    "preferences and instructions (for example which jobs they want). Use short markdown headings with "
    "bullets, under 400 words. Don't invent anything the sources don't say."
)


def _sha(text):
    return hashlib.sha1(text.encode()).hexdigest()


class Memory:
    def __init__(self, ws):
        self.ws = ws
        self.dir = ws.root / "memory"
        self.dir.mkdir(exist_ok=True)
        self.digests_path = self.dir / "digests.json"
        self.note_path = self.dir / "memory.md"
        self.note_meta_path = self.dir / "memory.json"

    def digests(self):
        return json.loads(self.digests_path.read_text()) if self.digests_path.exists() else {}

    def _save_digests(self, digests):
        tmp = self.digests_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(digests, indent=2))
        os.replace(tmp, self.digests_path)

    def note(self):
        return self.note_path.read_text() if self.note_path.exists() else ""

    def note_updated(self):
        if not self.note_meta_path.exists():
            return None
        return json.loads(self.note_meta_path.read_text()).get("updated")

    def _digests_hash(self, digests):
        return _sha(json.dumps(digests, sort_keys=True))

    def pending(self):
        """Files whose current text has no digest yet, most recently modified first."""
        if not self.ws.clean_docs.exists():
            return []
        digests = self.digests()
        todo = []
        for doc in iter_jsonl(self.ws.clean_docs):
            sha = _sha(doc["text"])
            if digests.get(doc["path"], {}).get("sha") != sha:
                try:
                    mtime = os.stat(doc["path"]).st_mtime
                except OSError:
                    mtime = 0
                todo.append((mtime, doc["path"], doc["text"], sha))
        todo.sort(reverse=True)
        return todo

    def _prune(self):
        """Forget digests of files that no longer exist in your folders."""
        if not self.ws.clean_docs.exists():
            return
        present = {doc["path"] for doc in iter_jsonl(self.ws.clean_docs)}
        digests = self.digests()
        kept = {p: d for p, d in digests.items() if p in present}
        if len(kept) != len(digests):
            self._save_digests(kept)

    def learn(self, brain, max_files=5, log=print):
        """Digest up to max_files new or changed files, then refresh the memory note if it is stale.

        Raises BrainUnavailable (usage limit, daily cap, ...) so the caller can pause Claude learning.
        """
        self._prune()
        done = 0
        for _, path, text, sha in self.pending()[:max_files]:
            log(f"Claude is reading {Path(path).name}")
            truncated = len(text) > MAX_FILE_CHARS
            body = text if not truncated else (
                text[:MAX_FILE_CHARS // 2] + "\n\n[... middle of the file left out for length ...]\n\n"
                + text[-MAX_FILE_CHARS // 2:])
            reply = brain.ask(f"File: {path}\n\n<file>\n{body}\n</file>\n\nWrite the digest.",
                              DIGEST_SYSTEM, kind="background", json_schema=DIGEST_SCHEMA)
            digest = reply["data"] or {"summary": reply["text"][:800], "facts": [], "tags": []}
            digests = self.digests()
            digests[path] = {
                "sha": sha,
                "summary": str(digest.get("summary", "")),
                "facts": [str(f) for f in digest.get("facts", [])][:12],
                "tags": [str(t) for t in digest.get("tags", [])][:8],
                "truncated": truncated,
                "updated": time.strftime("%Y-%m-%d %H:%M"),
            }
            self._save_digests(digests)
            done += 1
        self.refresh_note(brain, log)
        return done

    def refresh_note(self, brain, log=print):
        """Rebuild the memory note when file digests or what you said in chat changed."""
        from .chatlog import ChatLog
        digests = self.digests()
        said = ChatLog(self.ws).user_messages()
        if not digests and not said:
            return False
        digests_hash, chat_hash = self._digests_hash(digests), _sha(json.dumps(said))
        meta = json.loads(self.note_meta_path.read_text()) if self.note_meta_path.exists() else {}
        files_changed = meta.get("digests_hash") != digests_hash
        chat_changed = meta.get("chat_hash") != chat_hash
        # New chat messages alone refresh the note at most every 15 minutes.
        if not files_changed and (not chat_changed or time.time() - meta.get("updated_ts", 0) < 15 * 60):
            return False
        log("Claude is updating HomeGrok's memory of you")
        newest = sorted(digests.items(), key=lambda kv: kv[1]["updated"], reverse=True)[:150]
        lines = [f"- {Path(p).name} ({p}): {d['summary']} Facts: {'; '.join(d['facts'])}" for p, d in newest]
        told = "\n".join(f"- {m}" for m in said) or "(nothing yet)"
        prompt = (f"Current memory note:\n{self.note() or '(none yet)'}\n\n"
                  "Digests of the person's files:\n" + ("\n".join(lines) or "(none yet)") + "\n\n"
                  f"What the person told their assistant directly (oldest first; newer statements and anything "
                  f"they said directly win over the files):\n{told}\n\nWrite the updated memory note.")
        reply = brain.ask(prompt, MEMORY_SYSTEM, kind="background")
        self.note_path.write_text(reply["text"].strip() + "\n")
        self.note_meta_path.write_text(json.dumps({"digests_hash": digests_hash, "chat_hash": chat_hash,
                                                   "updated": time.strftime("%Y-%m-%d %H:%M"),
                                                   "updated_ts": time.time()}))
        return True
