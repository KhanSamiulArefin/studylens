"""A small, dependency-free BM25 keyword retriever.

BM25 is a strong baseline for course material, where questions usually reuse the
lecture's own terminology. The eval harness (next milestone) measures it, so it can
be compared against semantic/hybrid retrieval later.
"""

import math
import re
from collections import Counter

STOPWORDS = frozenset(
    """a an and are as at be but by can do does for from has have how i if in into is it its
    me my of on or so than that the their them then there these they this to was we what when
    where which who why will with would you your about explain tell describe define please"""
    # Words that describe the request, not the content ("summarize the main ideas of this lecture")
    """ summarize summarise summary overview recap lecture lectures notes slides chapter ideas main
    important covered here give""".split()
)

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_tokens = [Counter(tokenize(d)) for d in documents]
        self.doc_lens = [sum(c.values()) for c in self.doc_tokens]
        self.n = len(documents)
        self.avg_len = (sum(self.doc_lens) / self.n) if self.n else 0.0

        df: Counter[str] = Counter()
        for counts in self.doc_tokens:
            df.update(counts.keys())
        # BM25+ style idf floor so very common terms never contribute negatively
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = [0.0] * self.n
        if not terms or not self.n:
            return out
        for i, counts in enumerate(self.doc_tokens):
            norm = self.k1 * (1 - self.b + self.b * self.doc_lens[i] / (self.avg_len or 1))
            s = 0.0
            for t in terms:
                tf = counts.get(t)
                if tf:
                    s += self.idf[t] * tf * (self.k1 + 1) / (tf + norm)
            out[i] = s
        return out

    def top_k(self, query: str, k: int) -> list[tuple[int, float]]:
        scored = [(i, s) for i, s in enumerate(self.scores(query)) if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
