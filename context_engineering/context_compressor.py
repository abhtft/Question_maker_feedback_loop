"""
Context Engineering — Context Compressor
=========================================
Techniques 4, 5, 6: Trimming, Summarization, and Pruning.

Learning notes:
  - Technique 4 (Trimming): Cut context to a token budget. The key insight
    is HOW you cut — mid-word? mid-sentence? mid-paragraph? Each mode trades
    off precision vs. meaning preservation.
    
  - Technique 5 (Summarization): Use a cheap LLM to compress long context
    into a dense, focused summary. This is the most powerful compression
    technique but adds latency (one extra LLM call).
    
  - Technique 6 (Pruning): Remove low-value content BEFORE it reaches
    the LLM. Unlike trimming (which cuts by size), pruning cuts by
    quality/relevance. It prevents "context poisoning."
"""

import logging
import hashlib
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

# tiktoken may not be installed in all environments
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed. Token-based trimming will use "
                   "character approximation (1 token ≈ 4 chars).")


# ══════════════════════════════════════════════════════════════════════
# Technique 4: Trimming — ContextTrimmer
# ══════════════════════════════════════════════════════════════════════

class ContextTrimmer:
    """
    Trims context to fit within a token budget using three modes:
    
    1. hard_cutoff     — Cut at exact token count (fastest, may break mid-word)
    2. sentence_boundary — Cut at the nearest sentence end before the limit
    3. paragraph_boundary — Cut at the nearest paragraph break before the limit
    
    Why not always use paragraph_boundary?
      - It may cut too aggressively (dropping 200 tokens to reach a paragraph break
        when you have 50 tokens of headroom is wasteful).
      - For very short contexts, sentence_boundary is usually sufficient.
    
    The existing _truncate_to_tokens() in mylang4.py is equivalent to hard_cutoff mode.
    """

    SENTENCE_ENDINGS = {'.', '!', '?'}

    def _count_tokens(self, text: str, model: str = "gpt-4") -> int:
        """Count tokens in text. Falls back to character approximation."""
        if TIKTOKEN_AVAILABLE:
            try:
                enc = tiktoken.encoding_for_model(model)
                return len(enc.encode(text))
            except Exception:
                pass
        # Fallback: rough approximation (1 token ≈ 4 characters)
        return len(text) // 4

    def _hard_cutoff(self, text: str, max_tokens: int, model: str = "gpt-4") -> str:
        """
        Cut text at exact token count.
        
        Pros: Maximizes token usage, fastest
        Cons: Can break mid-word or mid-sentence
        
        This is what mylang4.py's _truncate_to_tokens() does.
        """
        if TIKTOKEN_AVAILABLE:
            try:
                enc = tiktoken.encoding_for_model(model)
                tokens = enc.encode(text)
                if len(tokens) <= max_tokens:
                    return text
                return enc.decode(tokens[:max_tokens])
            except Exception:
                pass
        # Fallback
        char_limit = max_tokens * 4
        return text[:char_limit]

    def _sentence_boundary(self, text: str, max_tokens: int, model: str = "gpt-4") -> str:
        """
        Cut at the nearest sentence end before the token limit.
        
        Algorithm:
          1. Hard-cut to token limit → get the raw cutoff point
          2. Walk backward from the cutoff to find the last sentence-ending character
          3. Cut there
        
        Pros: Preserves complete sentences (meaning is intact)
        Cons: May "waste" up to ~50 tokens of headroom
        
        Why this matters:
          "The quadratic formula is x = (-b ± √(b²-4ac))"  ← complete, useful
          "The quadratic formula is x = (-b ± √(b²-4a"      ← broken, useless
        """
        if self._count_tokens(text, model) <= max_tokens:
            return text

        # Get hard cutoff first
        hard_cut = self._hard_cutoff(text, max_tokens, model)
        
        # Walk backward to find last sentence ending
        for i in range(len(hard_cut) - 1, max(0, len(hard_cut) - 200), -1):
            if hard_cut[i] in self.SENTENCE_ENDINGS:
                return hard_cut[:i + 1]
        
        # No sentence boundary found within reasonable distance, use hard cutoff
        return hard_cut

    def _paragraph_boundary(self, text: str, max_tokens: int, model: str = "gpt-4") -> str:
        """
        Cut at the nearest paragraph break before the token limit.
        
        Algorithm:
          1. Split text into paragraphs
          2. Accumulate paragraphs until adding the next one would exceed the limit
          3. Return accumulated paragraphs
        
        Pros: Preserves complete ideas/sections
        Cons: Can be wasteful if paragraphs are long
        """
        if self._count_tokens(text, model) <= max_tokens:
            return text

        paragraphs = text.split('\n\n')
        result = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._count_tokens(para, model)
            if current_tokens + para_tokens > max_tokens:
                break
            result.append(para)
            current_tokens += para_tokens

        if not result:
            # Even the first paragraph exceeds the limit — fall back to sentence
            return self._sentence_boundary(paragraphs[0], max_tokens, model)

        return '\n\n'.join(result)

    def trim(self, text: str, max_tokens: int = 1000,
             mode: str = 'sentence_boundary', model: str = "gpt-4") -> str:
        """
        Trim text to a token budget using the specified mode.
        
        Args:
            text: The text to trim
            max_tokens: Maximum token count
            mode: 'hard_cutoff', 'sentence_boundary', or 'paragraph_boundary'
            model: Model name for tiktoken encoding
            
        Returns:
            Trimmed text within the token budget
        """
        if not text:
            return ""

        modes = {
            'hard_cutoff': self._hard_cutoff,
            'sentence_boundary': self._sentence_boundary,
            'paragraph_boundary': self._paragraph_boundary,
        }

        trimmer = modes.get(mode, self._sentence_boundary)
        if mode not in modes:
            logger.warning(f"Unknown trim mode '{mode}', using 'sentence_boundary'")

        result = trimmer(text, max_tokens, model)
        logger.debug(f"Trimmed: {self._count_tokens(text)} → {self._count_tokens(result)} tokens "
                      f"(mode={mode})")
        return result


# ══════════════════════════════════════════════════════════════════════
# Technique 5: Summarization (Context Distillation) — ContextSummarizer
# ══════════════════════════════════════════════════════════════════════

class ContextSummarizer:
    """
    Uses a (cheap) LLM call to compress retrieved context into a focused summary
    before it enters the main (expensive) generation prompt.
    
    Why summarize instead of just trimming?
      - Trimming is dumb: it drops content from the end, regardless of relevance
      - Summarization is smart: it extracts ONLY the relevant information
      - A 2000-token context about "algebra" that includes sections on history,
        applications, and exercises → summarizer extracts just the concepts
        needed for the specific topic
    
    The key is CONSTRAINT-BASED summarization:
      "Summarize ONLY facts about {topic} at {difficulty} level"
      This forces the model to filter, not just compress.
    
    Cost trade-off:
      - Extra LLM call (~100-300 tokens output)
      - But saves 1000+ tokens in the main prompt
      - Net cost is usually lower (or break-even) with better quality
    """

    SUMMARIZATION_PROMPT = """Summarize the following study material.

FOCUS: Extract ONLY information relevant to "{focus_topic}" at a {difficulty} difficulty level.
DISCARD: General introductions, administrative content, unrelated topics, and repetitive information.
FORMAT: Write a dense, factual summary. Use bullet points for key concepts. Keep it under 300 words.

Study Material:
{context}

Summary:"""

    def __init__(self, llm=None):
        """
        Args:
            llm: A LangChain LLM instance. If None, summarization is disabled
                 and the original text is returned unchanged.
        """
        self.llm = llm
        if not llm:
            logger.warning("ContextSummarizer initialized without LLM. "
                           "Summarization will be a no-op (passthrough).")

    def summarize(self, context: str, focus_topic: str = '',
                  difficulty: str = 'Medium') -> str:
        """
        Summarize context with a focus constraint.
        
        If no LLM is available or context is short (< 500 chars), returns
        the original context unchanged.
        
        Args:
            context: The raw context to summarize
            focus_topic: Topic to focus the summary on
            difficulty: Difficulty level (affects what detail level to keep)
            
        Returns:
            Summarized (or original) context string
        """
        # Guard: don't summarize short context (overhead not worth it)
        if not context or len(context) < 500:
            logger.debug("Context too short for summarization, returning as-is")
            return context

        if not self.llm:
            logger.debug("No LLM available, skipping summarization")
            return context

        try:
            prompt = self.SUMMARIZATION_PROMPT.format(
                focus_topic=focus_topic or "the given topic",
                difficulty=difficulty,
                context=context
            )

            response = self.llm.invoke(prompt)
            summary = response.content if hasattr(response, 'content') else str(response)

            # Sanity check: summary should be shorter than original
            if len(summary) >= len(context):
                logger.warning("Summarization produced longer output than input. "
                               "Returning original context.")
                return context

            logger.info(f"Summarized context: {len(context)} → {len(summary)} chars "
                         f"({100 - len(summary)*100//len(context)}% reduction)")
            return summary.strip()

        except Exception as e:
            logger.error(f"Summarization failed: {e}. Returning original context.")
            return context


# ══════════════════════════════════════════════════════════════════════
# Technique 6: Pruning (Quality Gating) — ContextPruner
# ══════════════════════════════════════════════════════════════════════

class ContextPruner:
    """
    Removes low-value content from context BEFORE it reaches the LLM.
    
    Unlike trimming (which cuts by size), pruning cuts by QUALITY/RELEVANCE.
    
    Three strategies (can be combined):
    
    1. min_quality — Paragraph-level quality scoring (has sentences? structure?)
       Already existed in mylang4.py as: quality_score > 0.3
    
    2. relevance_gate — Check if a paragraph contains topic-relevant keywords
       Prevents "context poisoning" (irrelevant content confusing the model)
    
    3. dedup — Remove near-duplicate paragraphs
       Common when ingesting multi-page PDFs (headers/footers repeat,
       same concept explained multiple times)
    
    IMPORTANT GOTCHA:
      Aggressive pruning can remove ALL content, leaving the LLM with nothing.
      Always check if result is empty and fall back to unpruned content.
    """

    def __init__(self, min_quality_threshold: float = 0.3,
                 min_paragraph_length: int = 50,
                 dedup_enabled: bool = True):
        self.min_quality_threshold = min_quality_threshold
        self.min_paragraph_length = min_paragraph_length
        self.dedup_enabled = dedup_enabled

    def _calculate_paragraph_quality(self, paragraph: str) -> float:
        """
        Score a paragraph's quality (0.0 to 1.0).
        
        This is the same logic as mylang4.py's _calculate_quality_score(),
        factored out into a reusable method.
        """
        text = paragraph.strip()
        if not text or len(text) < self.min_paragraph_length:
            return 0.0

        score = 0.0

        # Has complete sentences?
        sentences = [s for s in text.split('.') if len(s.strip()) > 10]
        if sentences:
            score += 0.4

        # Has paragraph structure?
        if len(text) > 100:
            score += 0.3

        # Has structural markers? (lists, colons, etc.)
        if any(char in text for char in [':', '-', '•', '*', '1.', '2.']):
            score += 0.3

        return min(score, 1.0)

    def _is_relevant(self, paragraph: str, topic_keywords: List[str] = None) -> bool:
        """
        Check if a paragraph is relevant to the given topic.
        
        A simple keyword-based relevance gate. For production, you'd use
        embedding similarity, but keyword matching is fast and interpretable.
        """
        if not topic_keywords:
            return True  # No keywords to filter by → keep everything

        text_lower = paragraph.lower()
        # Require at least one topic keyword to appear
        return any(kw.lower() in text_lower for kw in topic_keywords)

    def _get_paragraph_hash(self, paragraph: str) -> str:
        """
        Hash a paragraph for dedup.
        
        Uses a normalized version (lowercase, stripped, collapsed whitespace)
        to catch near-duplicates like:
          "The quadratic formula is..."  vs  "the  Quadratic  Formula  is..."
        """
        normalized = ' '.join(paragraph.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def prune(self, context: str, topic_keywords: List[str] = None) -> str:
        """
        Apply all pruning strategies to the context.
        
        Pipeline: split → quality gate → relevance gate → dedup → rejoin
        
        Args:
            context: Raw context string (paragraphs separated by double newlines)
            topic_keywords: Optional list of topic-relevant keywords for relevance gating
            
        Returns:
            Pruned context string. Falls back to original if pruning removes everything.
        """
        if not context:
            return ""

        paragraphs = context.split('\n\n')
        original_count = len(paragraphs)
        seen_hashes = set()
        kept = []

        for para in paragraphs:
            stripped = para.strip()
            if not stripped:
                continue

            # ── Strategy 1: Quality gate ──────────────────────────────
            quality = self._calculate_paragraph_quality(stripped)
            if quality < self.min_quality_threshold:
                logger.debug(f"Pruned (low quality {quality:.2f}): {stripped[:60]}...")
                continue

            # ── Strategy 2: Relevance gate ────────────────────────────
            if not self._is_relevant(stripped, topic_keywords):
                logger.debug(f"Pruned (irrelevant): {stripped[:60]}...")
                continue

            # ── Strategy 3: Dedup ─────────────────────────────────────
            if self.dedup_enabled:
                para_hash = self._get_paragraph_hash(stripped)
                if para_hash in seen_hashes:
                    logger.debug(f"Pruned (duplicate): {stripped[:60]}...")
                    continue
                seen_hashes.add(para_hash)

            kept.append(stripped)

        # CRITICAL: Fall back to original if pruning removed everything
        if not kept:
            logger.warning("Pruning removed ALL paragraphs! Falling back to original context.")
            return context

        pruned = '\n\n'.join(kept)
        logger.info(f"Pruned: {original_count} paragraphs → {len(kept)} paragraphs")
        return pruned
