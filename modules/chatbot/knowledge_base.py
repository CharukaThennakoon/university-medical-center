"""
modules/chatbot/knowledge_base.py - Lightweight RAG retrieval (no extra libraries).

The knowledge lives in  modules/chatbot/knowledge/center_kb.json  - a list of
entries:  {id, title, category, keywords[], content, always?}

For every question we:
  1. score each entry against the question (keyword matches count most, then
     title words, then words in the content, weighted by how rare the word is)
  2. take the best few entries + any entry marked "always": true
  3. inject those excerpts into the model's instructions

Details you have not filled in yet are written as  <<FILL IN: ...>>  in the JSON.
The assistant is told to treat such details as unknown instead of guessing.

Upgrade path (optional): replace score() with embedding similarity using
Gemini's embedding model; retrieve() keeps the same interface.
"""
import json
import logging
import math
import os
import re
from collections import Counter

log = logging.getLogger("umc.chatbot")

KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "knowledge", "center_kb.json")
PLACEHOLDER_RE = re.compile(r"<<FILL IN[^>]*>>")
FALLBACK_IDS = ("about", "services")  # used when nothing matches

STOPWORDS = {
    "a", "an", "the", "is", "are", "am", "was", "were", "be", "to", "of", "in", "on", "at",
    "for", "and", "or", "if", "it", "its", "i", "me", "my", "you", "your", "we", "do", "does",
    "did", "can", "could", "should", "would", "will", "what", "when", "which", "who", "how",
    "there", "this", "that", "with", "from", "by", "as", "about", "any", "some", "please",
    "tell", "need", "want", "get", "have", "has", "hi", "hello", "thanks", "thank", "much",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize(word):
    """Very light stemming so 'burns' matches 'burn' and 'hours' matches 'hour'."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text):
    return [_normalize(w) for w in _TOKEN_RE.findall((text or "").lower())
            if w not in STOPWORDS and len(w) > 1]


class Entry:
    def __init__(self, raw):
        self.id = raw["id"]
        self.title = raw["title"]
        self.category = raw.get("category", "")
        self.content = raw["content"]
        self.always = bool(raw.get("always", False))
        self.keywords = {_normalize(k.lower()) for k in raw.get("keywords", [])}
        self.title_tokens = set(tokenize(self.title))
        self.content_tokens = Counter(tokenize(self.content))

    @property
    def placeholders(self):
        return PLACEHOLDER_RE.findall(self.content)


class KnowledgeBase:
    def __init__(self, raw_entries):
        self.entries = []
        for raw in raw_entries:
            try:
                self.entries.append(Entry(raw))
            except (KeyError, TypeError, AttributeError):
                log.warning("Skipping a malformed knowledge base entry: %r", raw)
        n = max(len(self.entries), 1)
        df = Counter()
        for e in self.entries:
            for tok in e.keywords | e.title_tokens | set(e.content_tokens):
                df[tok] += 1
        # rarer words are worth more
        self.idf = {tok: math.log((n + 1) / (count + 1)) + 1 for tok, count in df.items()}

    # ------------------------------------------------------------------
    def _score(self, entry, query_tokens):
        score = 0.0
        for tok in query_tokens:
            idf = self.idf.get(tok)
            if idf is None:
                continue
            if tok in entry.keywords:
                score += 3 * idf
            if tok in entry.title_tokens:
                score += 2 * idf
            if tok in entry.content_tokens:
                score += idf
        return score

    def retrieve(self, query, top_k=4, min_score=1.5, max_chars=6000):
        """Returns a list of Entry objects (best matches first, then 'always' entries)."""
        query_tokens = set(tokenize(query))
        scored = sorted(((self._score(e, query_tokens), e) for e in self.entries),
                        key=lambda pair: -pair[0])
        picked = [e for s, e in scored[:top_k] if s >= min_score]

        if not picked:  # nothing matched: give the model the basics
            picked = [e for e in self.entries if e.id in FALLBACK_IDS]
        for e in self.entries:
            if e.always and e not in picked:
                picked.append(e)

        result, total = [], 0
        for e in picked:  # respect a size budget
            total += len(e.content) + len(e.title)
            if total > max_chars and result:
                break
            result.append(e)
        return result

    def unfilled_placeholders(self):
        return [(e.id, p) for e in self.entries for p in e.placeholders]


# ----------------------------------------------------------------------
_kb = None


def load_knowledge_base(path=KB_PATH):
    """Loads (or reloads) the knowledge base. Never raises - an empty KB is returned on error."""
    global _kb
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("the JSON file must contain a list of entries")
        _kb = KnowledgeBase(data)
    except (OSError, ValueError) as e:
        log.error("Could not load the chatbot knowledge base (%s): %s", path, e)
        _kb = KnowledgeBase([])
    missing = _kb.unfilled_placeholders()
    if missing:
        log.warning("Chatbot knowledge base: %d detail(s) still marked <<FILL IN>> "
                    "(edit %s).", len(missing), os.path.relpath(path))
    return _kb


def get_kb():
    return _kb if _kb is not None else load_knowledge_base()
