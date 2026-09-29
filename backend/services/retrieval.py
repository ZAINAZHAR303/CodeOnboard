import math
import re
from collections import Counter

from models.schemas import FileInfo
from utils.file_helpers import is_code

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "in", "on", "for", "and", "or", "with", "how", "what",
    "where", "why", "when", "which", "who", "do", "does", "did", "i", "we", "you", "it", "this", "that", "these", "those",
    "can", "should", "would", "could", "my", "our", "your", "me", "from", "by", "as", "at", "about", "into", "add", "new",
    "use", "used", "using", "make", "need", "want", "there", "their", "they", "them", "if", "so", "be", "has", "have",
    "file", "files", "code", "project", "codebase", "repo", "repository", "please", "explain", "work", "works", "some",
    "any", "all", "also", "will", "able", "implement",
}

_SPLIT_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN.findall(text):
        for part in _SPLIT_CAMEL.sub(" ", raw).split():
            for piece in part.lower().split("_"):
                if len(piece) > 2 and piece not in STOP_WORDS:
                    tokens.append(_stem(piece))
    return tokens


def _stem(word: str) -> str:
    for suffix in ("ing", "ies", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


class FileRetriever:
    """Small BM25 index over file paths and contents."""

    def __init__(self, files: list[FileInfo]) -> None:
        self.files = [f for f in files if is_code(f.language) or f.language in {"Markdown", "YAML", "JSON", "TOML", "HTML"}]
        self.doc_terms: list[Counter[str]] = []
        self.path_terms: list[set[str]] = []
        doc_freq: Counter[str] = Counter()
        for f in self.files:
            terms = Counter(tokenize(f.content[:20000]))
            path_terms = set(tokenize(f.path))
            self.doc_terms.append(terms)
            self.path_terms.append(path_terms)
            doc_freq.update(set(terms) | path_terms)
        self.doc_freq = doc_freq
        self.avg_len = (sum(sum(t.values()) for t in self.doc_terms) / len(self.doc_terms)) if self.doc_terms else 1.0

    def search(self, query: str, limit: int = 8) -> list[tuple[FileInfo, float]]:
        query_terms = set(tokenize(query))
        if not query_terms or not self.files:
            return []
        n = len(self.files)
        scored: list[tuple[FileInfo, float]] = []
        for f, terms, path_terms in zip(self.files, self.doc_terms, self.path_terms):
            length = sum(terms.values()) or 1
            score = 0.0
            for term in query_terms:
                df = self.doc_freq.get(term, 0)
                if not df:
                    continue
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                tf = terms.get(term, 0)
                if tf:
                    score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / self.avg_len))
                if term in path_terms:
                    score += idf * 2.5
            if score > 0:
                if f.language == "Markdown":
                    score *= 0.6
                scored.append((f, score))
        scored.sort(key=lambda item: -item[1])
        return scored[:limit]
