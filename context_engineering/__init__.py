"""
Context Engineering Module
==========================
A learning-oriented implementation of 10 context engineering techniques,
built to enhance the Question Paper Generator pipeline.

Techniques covered:
  Family A — Dynamic Prompt Selection (prompt_router.py)
    1. Classified Parameter Routing
    2. Template-Data Separation
    3. Few-Shot Example Injection

  Family B — Context Compression (context_compressor.py)
    4. Trimming (Token Truncation)
    5. Summarization (Context Distillation)
    6. Pruning (Quality Gating)

  Family C — Context Placement (context_placer.py)
    7. Strategic Ordering (Primacy/Recency)
    8. Sliding Window + Anchoring

  Family D — Retrieval & Caching (context_cache.py)
    9. RAG with Reranking (documented, existing in mylang4.py)
   10. Semantic Caching

Usage:
    from context_engineering import ContextEngineeringPipeline
    
    pipeline = ContextEngineeringPipeline()
    assembled_prompt = pipeline.run(topic_data, raw_context)
"""

from context_engineering.prompt_router import PromptRouter, PromptLibrary, FewShotSelector
from context_engineering.context_compressor import ContextTrimmer, ContextSummarizer, ContextPruner
from context_engineering.context_placer import ContextPlacer, SlidingWindowManager
from context_engineering.context_cache import SemanticCache

import logging

logger = logging.getLogger(__name__)


class ContextEngineeringPipeline:
    """
    Orchestrates all 10 context engineering techniques into a single pipeline.
    
    Pipeline flow:
        1. ROUTE    → Pick the best prompt template       (Technique 1)
        2. SEPARATE → Load template + fill with data      (Technique 2)
        3. PRUNE    → Remove low-quality/irrelevant       (Technique 6)
        4. TRIM     → Cut to token budget                 (Technique 4)
        5. SUMMARIZE→ Compress if still too long           (Technique 5)
        6. FEW-SHOT → Inject matching examples            (Technique 3)
        7. PLACE    → Order sections for max attention    (Technique 7)
        8. CACHE?   → Check semantic cache first          (Technique 10)
        9. WINDOW   → Manage revision history             (Technique 8)
    
    Each step is optional and configurable.
    """

    def __init__(self, llm=None, embeddings=None, config=None):
        """
        Args:
            llm: LangChain LLM instance (used by summarizer)
            embeddings: Embedding model (used by semantic cache)
            config: dict with optional overrides:
                - enable_summarization (bool): default False
                - enable_cache (bool): default True
                - trim_mode (str): 'hard_cutoff' | 'sentence_boundary' | 'paragraph_boundary'
                - max_tokens (int): default 1000
                - cache_threshold (float): default 0.92
                - few_shot_count (int): default 2
        """
        config = config or {}

        # Initialize all components
        self.prompt_library = PromptLibrary()
        self.router = PromptRouter(self.prompt_library)
        self.few_shot_selector = FewShotSelector()
        self.trimmer = ContextTrimmer()
        self.pruner = ContextPruner()
        self.placer = ContextPlacer()
        self.window_manager = SlidingWindowManager()

        # Optional components (require LLM / embeddings)
        self.summarizer = ContextSummarizer(llm) if llm and config.get('enable_summarization', False) else None
        self.cache = SemanticCache(embeddings) if embeddings and config.get('enable_cache', True) else None

        # Configuration
        self.trim_mode = config.get('trim_mode', 'sentence_boundary')
        self.max_tokens = config.get('max_tokens', 1000)
        self.cache_threshold = config.get('cache_threshold', 0.92)
        self.few_shot_count = config.get('few_shot_count', 2)

        logger.info(f"ContextEngineeringPipeline initialized. "
                     f"Summarizer: {'ON' if self.summarizer else 'OFF'}, "
                     f"Cache: {'ON' if self.cache else 'OFF'}, "
                     f"Trim mode: {self.trim_mode}")

    def run(self, topic_data: dict, raw_context: str, attempt: int = 0,
            previous_feedback: dict = None) -> dict:
        """
        Run the full context engineering pipeline.

        Args:
            topic_data: Request parameters (subject, difficulty, bloom, etc.)
            raw_context: Raw retrieved context from vectorstore
            attempt: Current attempt number (0-based) for sliding window
            previous_feedback: Verification feedback from previous attempt

        Returns:
            dict with keys:
                - 'template': The selected prompt template string
                - 'context': The processed context (pruned, trimmed, summarized)
                - 'few_shot_examples': List of example dicts to inject
                - 'cache_hit': bool, whether a cached response was found
                - 'cached_response': The cached response (if cache_hit is True)
                - 'revision_history': Summarized history for sliding window
        """
        subject = topic_data.get('subjectName', 'General')
        difficulty = topic_data.get('difficulty', 'Medium')
        bloom_level = topic_data.get('bloomLevel', 'Remember')
        question_type = topic_data.get('questionType', 'MCQ')

        result = {
            'cache_hit': False,
            'cached_response': None,
            'revision_history': '',
        }

        # ── Step 1: Check semantic cache (Technique 10) ────────────────
        if self.cache and attempt == 0:
            cache_key = self.cache.build_key(topic_data)
            cached = self.cache.get(cache_key, threshold=self.cache_threshold)
            if cached is not None:
                logger.info("Semantic cache HIT — returning cached response")
                result['cache_hit'] = True
                result['cached_response'] = cached
                return result

        # ── Step 2: Route to best template (Technique 1 + 2) ───────────
        template = self.router.select_template(
            subject=subject,
            difficulty=difficulty,
            bloom_level=bloom_level,
            question_type=question_type
        )
        result['template'] = template
        logger.info(f"Routed to template: {self.router.last_route_key}")

        # ── Step 3: Prune context (Technique 6) ────────────────────────
        pruned_context = self.pruner.prune(raw_context)
        logger.info(f"Pruned context: {len(raw_context)} → {len(pruned_context)} chars")

        # ── Step 4: Trim to token budget (Technique 4) ─────────────────
        trimmed_context = self.trimmer.trim(
            pruned_context,
            max_tokens=self.max_tokens,
            mode=self.trim_mode
        )
        logger.info(f"Trimmed context: {len(pruned_context)} → {len(trimmed_context)} chars")

        # ── Step 5: Summarize if still large (Technique 5) ─────────────
        if self.summarizer and len(trimmed_context) > 500:
            trimmed_context = self.summarizer.summarize(
                trimmed_context,
                focus_topic=topic_data.get('sectionName', ''),
                difficulty=difficulty
            )
            logger.info(f"Summarized context to {len(trimmed_context)} chars")

        result['context'] = trimmed_context

        # ── Step 6: Select few-shot examples (Technique 3) ─────────────
        examples = self.few_shot_selector.select(
            subject=subject,
            difficulty=difficulty,
            bloom_level=bloom_level,
            question_type=question_type,
            count=self.few_shot_count
        )
        result['few_shot_examples'] = examples
        logger.info(f"Selected {len(examples)} few-shot examples")

        # ── Step 7: Manage sliding window (Technique 8) ────────────────
        if attempt > 0 and previous_feedback:
            revision_history = self.window_manager.update(
                attempt=attempt,
                feedback=previous_feedback
            )
            result['revision_history'] = revision_history
            logger.info(f"Sliding window: revision history = {len(revision_history)} chars")

        # ── Step 8: Strategic ordering is handled at assembly time ──────
        # The ContextPlacer.assemble() method applies Technique 7
        # It's called by the consumer (QuestionGenerator) when building
        # the final prompt string.

        return result

    def assemble_prompt(self, pipeline_result: dict, topic_data: dict) -> str:
        """
        Assemble the final prompt using strategic ordering (Technique 7).
        
        Args:
            pipeline_result: Output from self.run()
            topic_data: Original request data
            
        Returns:
            Fully assembled prompt string ready for LLM
        """
        return self.placer.assemble(
            template=pipeline_result['template'],
            context=pipeline_result['context'],
            few_shot_examples=pipeline_result['few_shot_examples'],
            topic_data=topic_data,
            revision_history=pipeline_result.get('revision_history', '')
        )

    def cache_response(self, topic_data: dict, response: dict):
        """Store a successful response in the semantic cache."""
        if self.cache:
            cache_key = self.cache.build_key(topic_data)
            self.cache.put(cache_key, response)
            logger.info("Response stored in semantic cache")
