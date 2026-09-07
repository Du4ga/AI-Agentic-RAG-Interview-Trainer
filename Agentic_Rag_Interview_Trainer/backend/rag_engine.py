"""
RAG Engine — FAISS-based retrieval over interview knowledge base
"""
import os
import json
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

KB_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge_base")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80


class RAGEngine:
    def __init__(self):
        self._index = None
        self._chunks: List[Dict] = []
        self._embedder = None
        self._ready = False
        self._load_or_build()

    def _load_or_build(self):
        try:
            self.build_index()
        except Exception as e:
            logger.warning(f"RAG build deferred: {e}")

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embedder

    def build_index(self) -> int:
        """Build FAISS index from all .txt/.json/.md files in knowledge_base/."""
        import faiss

        kb_path = Path(KB_DIR)
        if not kb_path.exists():
            raise FileNotFoundError(f"Knowledge base directory not found: {KB_DIR}")

        docs = []
        for ext in ["*.txt", "*.md", "*.json"]:
            for fpath in kb_path.rglob(ext):
                try:
                    text = fpath.read_text(encoding="utf-8")
                    if fpath.suffix == ".json":
                        data = json.loads(text)
                        if isinstance(data, list):
                            for item in data:
                                docs.append({
                                    "text": item.get("content", str(item)),
                                    "source": fpath.name,
                                    "category": item.get("category", "general"),
                                    "tags": item.get("tags", [])
                                })
                        else:
                            docs.append({"text": str(data), "source": fpath.name, "category": "general", "tags": []})
                    else:
                        docs.append({"text": text, "source": fpath.name, "category": "general", "tags": []})
                except Exception as e:
                    logger.warning(f"Skipping {fpath}: {e}")

        if not docs:
            raise ValueError("No documents found in knowledge base")

        # Chunk documents
        self._chunks = []
        for doc in docs:
            chunks = _split_text(doc["text"], CHUNK_SIZE, CHUNK_OVERLAP)
            for c in chunks:
                self._chunks.append({
                    "text": c,
                    "source": doc["source"],
                    "category": doc["category"],
                    "tags": doc["tags"]
                })

        logger.info(f"Chunked {len(docs)} docs into {len(self._chunks)} chunks")

        # Embed and build FAISS index
        embedder = self._get_embedder()
        texts = [c["text"] for c in self._chunks]
        embeddings = embedder.encode(texts, batch_size=64, show_progress_bar=False)
        embeddings = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(embeddings)

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)
        self._ready = True
        logger.info(f"FAISS index built: {self._index.ntotal} vectors, dim={dim}")
        return len(self._chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_category: Optional[str] = None
    ) -> List[Dict]:
        """Retrieve top_k relevant chunks for a query."""
        if not self._ready or self._index is None:
            logger.warning("RAG index not ready; returning empty context")
            return []

        import faiss
        embedder = self._get_embedder()
        q_emb = embedder.encode([query], show_progress_bar=False)
        q_emb = np.array(q_emb, dtype=np.float32)
        faiss.normalize_L2(q_emb)

        k = min(top_k * 3, len(self._chunks))
        scores, indices = self._index.search(q_emb, k)

        results = []
        seen_texts = set()
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            chunk = self._chunks[idx]
            if filter_category and chunk["category"] != filter_category:
                continue
            text_sig = chunk["text"][:80]
            if text_sig in seen_texts:
                continue
            seen_texts.add(text_sig)
            results.append({"score": float(score), **chunk})
            if len(results) >= top_k:
                break

        return results

    def is_ready(self) -> bool:
        return self._ready

    def format_context(self, chunks: List[Dict], max_chars: int = 2000) -> str:
        """Format retrieved chunks into a context string for the prompt."""
        parts = []
        total = 0
        for c in chunks:
            snippet = c["text"].strip()
            if total + len(snippet) > max_chars:
                snippet = snippet[: max_chars - total]
                parts.append(snippet)
                break
            parts.append(snippet)
            total += len(snippet)
        return "\n\n---\n\n".join(parts)


def _split_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks at sentence/paragraph boundaries."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # Overlap: take last `overlap` chars from previous chunk
            overlap_text = current[-overlap:] if overlap and current else ""
            current = (overlap_text + " " + para).strip() if overlap_text else para
    if current:
        chunks.append(current)
    return chunks if chunks else [text[:chunk_size]]
