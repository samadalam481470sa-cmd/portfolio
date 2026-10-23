"""One knowledge layer. Every source HomeGrok has is searched together, and every answer cites them.

Sources: the public corpus (Wikipedia and job-posting text), the Cortex memory of that public text,
confirmed-open jobs, real Hub deals, your saved answers, and your chat with HomeGrok.
Your personal computer files are NOT searched here.
"""
import json
import pickle

from .vectordb import Index

GROUPS = {"public": "public web text", "cortex": "learned public memory", "jobs": "confirmed-open job",
          "deals": "real Hub deal", "answers": "your saved answer", "chat": "your chat with HomeGrok"}


def _public_index(ws):
    """Index of the public corpus, rebuilt only when that corpus has grown."""
    corpus = ws.public_docs
    if not corpus.exists():
        return None
    size = corpus.stat().st_size
    cache = ws.root / "public_index.pkl"
    if cache.exists():
        with open(cache, "rb") as f:
            saved = pickle.load(f)
        if saved["size"] == size:
            return saved["index"]
    idx = Index()
    with open(corpus, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if line.strip():
                idx.add(str(i), json.loads(line)["text"])
    idx.finalize()
    with open(cache, "wb") as f:
        pickle.dump({"size": size, "index": idx}, f)
    return idx


def _small_items(ws):
    """Jobs, deals, saved answers and chat: small enough to index on each question."""
    items = []
    try:
        from .jobs import JobScout
        for j in JobScout(ws).confirmed_open(40):
            items.append(("jobs", j["title"] + " at " + j["company"], f"{j['title']} at {j['company']}: {j['url']}"))
    except Exception:
        pass
    try:
        from .connections import hub_deals
        for d in hub_deals(limit=20):
            items.append(("deals", d.get("name", ""), f"{d.get('name')}: profit ${d.get('profit', 0):.2f} "
                          f"buy {d.get('buy_source')} sell {d.get('sell_source')}"))
    except Exception:
        pass
    cfg = ws.load_config().get("apply_answers", {})
    for k, v in cfg.items():
        if k != "custom":
            items.append(("answers", k, f"{k}: {v}"))
    for k, v in cfg.get("custom", {}).items():
        items.append(("answers", k[:80], f"{k[:80]}: {v}"))
    try:
        from .chatlog import ChatLog
        for e in ChatLog(ws).recent(300):
            items.append(("chat", e["role"], f"{e['role']}: {e['text'][:600]}"))
    except Exception:
        pass
    return items


def search(ws, question, k=8):
    """Search all sources together. Returns numbered sources: [{id, group, title, text}]."""
    found = []
    pub = _public_index(ws)
    if pub is not None:
        for h in pub.search(question, 4):
            found.append({"group": "public", "title": "public web text", "text": h["text"]})
    try:
        from .cortex_bot import PublicCortex
        for r in PublicCortex(ws).recall(question, k=2):
            found.append({"group": "cortex", "title": r.get("title", ""), "text": r.get("text", "")})
    except Exception:
        pass
    items = _small_items(ws)
    if items:
        idx = Index()
        for i, (_, _, text) in enumerate(items):
            idx.add(str(i), text)
        idx.finalize()
        for h in idx.search(question, 6):
            group, title, text = items[int(h["path"])]
            found.append({"group": group, "title": title, "text": text})
    seen, out = set(), []
    for item in found:
        key = item["text"][:80]
        if key in seen or not item["text"].strip():
            continue
        seen.add(key)
        item["id"] = len(out) + 1
        item["label"] = GROUPS.get(item["group"], item["group"])
        out.append(item)
        if len(out) >= k:
            break
    return out


def answer(ws, question):
    """Answer from the sources, citing them as [n]. Returns {text, sources}."""
    sources = search(ws, question)
    if not sources:
        return {"text": "", "sources": []}
    block = "\n".join(f"[{s['id']}] ({s['label']}) {s['title']}: {s['text'][:700]}" for s in sources)
    from .brain import ClaudeBrain
    system = ("You answer from the numbered sources given. Cite the source number in brackets after each claim you "
              "use, like [2]. Never invent facts that are not in the sources. Where sources conflict, say so.")
    reply = ClaudeBrain(ws).ask(f"<sources>\n{block}\n</sources>\n\nQuestion: {question}", system, kind="chat")
    return {"text": reply["text"].strip(), "sources": sources}
