"""WOLF's long-term memory, stored as plain files in WOLF_HOME (default ~/.wolf).

  profile.md       core facts about you, in `## sections` (always in WOLF's context)
  memories.jsonl   individual memories: {id, text, tags, created, updated}
  journal.md       one-line summary per conversation, newest last

Everything is human-readable and editable. It lives outside the repository on purpose:
it's personal data and must never be committed.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_WORD = re.compile(r"[a-z0-9']+")
_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "be",
    "i", "me", "my", "you", "your", "it", "that", "this", "with", "at", "as", "do", "what",
    "who", "how", "when", "where", "about", "have", "has", "like", "likes",
}


def default_home() -> Path:
    return Path(os.environ.get("WOLF_HOME", Path.home() / ".wolf")).expanduser()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


@dataclass
class Memory:
    id: str
    text: str
    tags: list[str] = field(default_factory=list)
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    def line(self) -> str:
        tags = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"{self.id}: {self.text}{tags}"


class MemoryStore:
    def __init__(self, home: str | Path | None = None):
        self.home = Path(home).expanduser() if home else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.home, 0o700)  # personal data: owner-only
        except OSError:
            pass
        self.memories_path = self.home / "memories.jsonl"
        self.profile_path = self.home / "profile.md"
        self.journal_path = self.home / "journal.md"

    # ---------- memories ----------
    def all(self) -> list[Memory]:
        if not self.memories_path.exists():
            return []
        out = []
        for line in self.memories_path.read_text("utf-8").splitlines():
            if line.strip():
                try:
                    out.append(Memory(**json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue  # skip a hand-edited line that no longer parses
        return out

    def _save(self, memories: list[Memory]) -> None:
        tmp = self.memories_path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(asdict(m), ensure_ascii=False) + "\n" for m in memories), "utf-8")
        tmp.replace(self.memories_path)

    def add(self, text: str, tags: list[str] | None = None) -> Memory:
        text = text.strip()
        if not text:
            raise ValueError("Memory text is empty")
        mems = self.all()
        for m in mems:
            if m.text.lower() == text.lower():
                return m  # already known
        next_id = 1 + max((int(m.id[1:]) for m in mems if m.id[1:].isdigit()), default=0)
        mem = Memory(id=f"m{next_id}", text=text, tags=sorted({t.strip().lower() for t in tags or [] if t.strip()}))
        mems.append(mem)
        self._save(mems)
        return mem

    def update(self, mem_id: str, text: str) -> Memory:
        mems = self.all()
        for m in mems:
            if m.id == mem_id:
                m.text, m.updated = text.strip(), _now()
                self._save(mems)
                return m
        raise KeyError(mem_id)

    def forget(self, mem_id: str) -> Memory:
        mems = self.all()
        for i, m in enumerate(mems):
            if m.id == mem_id:
                del mems[i]
                self._save(mems)
                return m
        raise KeyError(mem_id)

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        q = _terms(query)
        scored = []
        for m in self.all():
            words = _terms(m.text)
            score = 2 * len(q & set(m.tags)) + len(q & words)
            # partial-word matches (e.g. "run" ~ "running") count for less
            score += 0.5 * sum(1 for t in q for w in words if t != w and (w.startswith(t) or t.startswith(w)) and min(len(t), len(w)) >= 3)
            if score:
                scored.append((score, m.updated, m))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [m for _, _, m in scored[:limit]]

    def recent(self, limit: int = 150) -> list[Memory]:
        return sorted(self.all(), key=lambda m: m.updated, reverse=True)[:limit]

    # ---------- profile ----------
    def profile(self) -> str:
        return self.profile_path.read_text("utf-8") if self.profile_path.exists() else ""

    def update_profile(self, section: str, content: str) -> None:
        text = self.profile() or "# About me\n"
        header = f"## {section.strip()}"
        block = f"{header}\n\n{content.strip()}\n"
        pattern = re.compile(rf"^{re.escape(header)}\s*\n.*?(?=^## |\Z)", re.S | re.M)
        if pattern.search(text):
            text = pattern.sub(lambda _m: block + "\n", text, count=1)
        else:
            text = text.rstrip() + "\n\n" + block
        self.profile_path.write_text(text.rstrip() + "\n", "utf-8")

    # ---------- journal ----------
    def add_journal(self, summary: str) -> None:
        summary = " ".join(summary.split())
        if not summary:
            return
        with self.journal_path.open("a", encoding="utf-8") as f:
            f.write(f"- {datetime.now().strftime('%Y-%m-%d %H:%M')}: {summary}\n")

    def recent_journal(self, n: int = 10) -> list[str]:
        if not self.journal_path.exists():
            return []
        lines = [l for l in self.journal_path.read_text("utf-8").splitlines() if l.startswith("- ")]
        return lines[-n:]
