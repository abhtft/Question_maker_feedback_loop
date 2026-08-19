"""
Context Engineering — Semantic Cache
======================================
Technique 10: Semantic Caching.

Learning notes:
  Semantic caching stores LLM responses and matches new requests by MEANING
  (embedding similarity) rather than exact string match.
  
  Why semantic and not exact-match?
    Request A: "Generate 5 Hard MCQs on Quadratic Equations for Grade 10"
    Request B: "5 difficult MCQ questions about Quadratic Equations, Class 10"
    
    These are semantically identical (should return same result),
    but have zero exact string overlap beyond common words.
    
    A semantic cache embeds both requests into vector space and finds
    they are ~0.97 similar → cache HIT.
  
  Trade-offs:
    - Saves LLM API costs (no call needed for cache hits)
    - Reduces latency dramatically
    - BUT: in education, teachers may WANT different questions each time
      for the same topic → provide a bypass_cache flag
    - Cache must be invalidated when prompt templates change
      (a v2 prompt should not serve v1 cached results)
"""

import json
import time
import hashlib
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# numpy may not be installed in all environments
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("numpy not installed. Semantic cache will use a simplified "
                   "similarity metric.")


class SemanticCache:
    """
    In-memory semantic cache for LLM responses.
    
    How it works:
    
    1. BUILD KEY: Convert request params into a canonical string
       (e.g., "math|hard|analyze|mcq|5|quadratic equations")
    
    2. EMBED: Convert the key string into a vector using the same
       embedding model used for RAG retrieval
    
    3. SEARCH: On a new request, embed its key and compare against
       all cached entries using cosine similarity
    
    4. HIT/MISS:
       - similarity > threshold (e.g., 0.92) → return cached response
       - similarity < threshold → call LLM, cache the response
    
    5. EVICTION: Entries older than TTL (time-to-live) are evicted
       to prevent stale results
    
    For production, you'd use Redis + FAISS or a managed vector DB.
    This in-memory implementation is for learning purposes.
    """

    def __init__(self, embeddings=None, ttl_seconds: int = 3600,
                 max_entries: int = 100):
        """
        Args:
            embeddings: LangChain embeddings model (e.g., OpenAIEmbeddings).
                If None, falls back to exact-match caching.
            ttl_seconds: Time-to-live for cache entries (default: 1 hour)
            max_entries: Maximum number of cached entries
        """
        self.embeddings = embeddings
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        # Cache storage: list of {key_str, embedding, response, timestamp}
        self._cache: List[Dict[str, Any]] = []

        mode = "semantic (embedding-based)" if embeddings else "exact-match (fallback)"
        logger.info(f"SemanticCache initialized: mode={mode}, "
                     f"TTL={ttl_seconds}s, max_entries={max_entries}")

    def build_key(self, topic_data: Dict[str, Any]) -> str:
        """
        Build a canonical cache key from request parameters.
        
        The key is a normalized string that captures the "identity" of a request.
        Two requests with the same key should produce the same output.
        
        Note: We deliberately EXCLUDE 'additionalInstructions' from the key
        because free-text instructions are likely unique per request and
        would cause cache misses on every call.
        """
        parts = [
            topic_data.get('subjectName', '').lower().strip(),
            topic_data.get('difficulty', '').lower().strip(),
            topic_data.get('bloomLevel', '').lower().strip(),
            topic_data.get('questionType', '').lower().strip(),
            str(topic_data.get('numQuestions', 1)),
            topic_data.get('sectionName', '').lower().strip(),
            topic_data.get('classGrade', '').lower().strip(),
        ]
        key = '|'.join(parts)
        logger.debug(f"Cache key: {key}")
        return key

    def _embed(self, text: str) -> Optional[List[float]]:
        """Embed a text string. Returns None if embeddings not available."""
        if not self.embeddings:
            return None
        try:
            return self.embeddings.embed_query(text)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """
        Compute cosine similarity between two vectors.
        
        Cosine similarity = dot(A, B) / (||A|| × ||B||)
        
        Range: [-1, 1] where 1 = identical, 0 = orthogonal, -1 = opposite
        For text embeddings, values are typically in [0, 1].
        """
        if NUMPY_AVAILABLE:
            a = np.array(vec_a)
            b = np.array(vec_b)
            dot = np.dot(a, b)
            norm = np.linalg.norm(a) * np.linalg.norm(b)
            if norm == 0:
                return 0.0
            return float(dot / norm)
        else:
            # Manual calculation without numpy
            dot = sum(x * y for x, y in zip(vec_a, vec_b))
            norm_a = sum(x ** 2 for x in vec_a) ** 0.5
            norm_b = sum(x ** 2 for x in vec_b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

    def _evict_expired(self):
        """Remove cache entries older than TTL."""
        now = time.time()
        before = len(self._cache)
        self._cache = [
            entry for entry in self._cache
            if (now - entry['timestamp']) < self.ttl_seconds
        ]
        evicted = before - len(self._cache)
        if evicted > 0:
            logger.info(f"Evicted {evicted} expired cache entries")

    def _evict_overflow(self):
        """Remove oldest entries if cache exceeds max_entries."""
        if len(self._cache) > self.max_entries:
            overflow = len(self._cache) - self.max_entries
            self._cache = sorted(self._cache, key=lambda x: x['timestamp'])
            self._cache = self._cache[overflow:]
            logger.info(f"Evicted {overflow} entries due to cache overflow")

    def get(self, key: str, threshold: float = 0.92) -> Optional[Dict[str, Any]]:
        """
        Look up a response in the cache.
        
        For semantic mode: finds the most similar cached key above the threshold.
        For exact-match mode: requires exact key string match.
        
        Args:
            key: Cache key string (from build_key)
            threshold: Minimum cosine similarity for a hit (0.0 to 1.0)
            
        Returns:
            Cached response dict, or None if no match found
        """
        self._evict_expired()

        if not self._cache:
            return None

        # ── Semantic matching (if embeddings available) ───────────────
        if self.embeddings:
            query_embedding = self._embed(key)
            if query_embedding is None:
                # Embedding failed, fall back to exact match
                return self._exact_match(key)

            best_similarity = 0.0
            best_entry = None

            for entry in self._cache:
                if entry.get('embedding') is None:
                    continue
                similarity = self._cosine_similarity(query_embedding, entry['embedding'])
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_entry = entry

            if best_entry and best_similarity >= threshold:
                logger.info(f"Cache HIT (semantic): similarity={best_similarity:.4f}, "
                             f"threshold={threshold}")
                return best_entry['response']
            else:
                logger.debug(f"Cache MISS (semantic): best_similarity="
                              f"{best_similarity:.4f}, threshold={threshold}")
                return None

        # ── Exact-match fallback ──────────────────────────────────────
        return self._exact_match(key)

    def _exact_match(self, key: str) -> Optional[Dict[str, Any]]:
        """Exact string match fallback when embeddings are unavailable."""
        for entry in self._cache:
            if entry['key_str'] == key:
                logger.info("Cache HIT (exact match)")
                return entry['response']
        logger.debug("Cache MISS (exact match)")
        return None

    def put(self, key: str, response: Dict[str, Any]):
        """
        Store a response in the cache.
        
        Args:
            key: Cache key string (from build_key)
            response: The LLM response to cache
        """
        # Create embedding for semantic matching
        embedding = self._embed(key) if self.embeddings else None

        entry = {
            'key_str': key,
            'embedding': embedding,
            'response': response,
            'timestamp': time.time(),
        }

        self._cache.append(entry)
        self._evict_overflow()

        logger.info(f"Cached response (total entries: {len(self._cache)})")

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
        logger.info("Cache cleared")

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        self._evict_expired()
        return {
            'total_entries': len(self._cache),
            'max_entries': self.max_entries,
            'ttl_seconds': self.ttl_seconds,
            'mode': 'semantic' if self.embeddings else 'exact_match',
        }
