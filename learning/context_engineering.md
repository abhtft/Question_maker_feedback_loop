# Context Engineering & Dynamic Prompting — Learning Reference

> **What is Context Engineering?**
> Context engineering is the discipline of designing the *information environment* an LLM sees at inference time.
> While prompt engineering focuses on *what words to say*, context engineering focuses on *what information to include, how to arrange it, and what to leave out*.

---

## How This Document Works

Each technique below is explained conceptually AND implemented in this project's `context_engineering/` module.
Cross-references point you to the exact file and class so you can study the working code.

---

## Family A: Dynamic Prompt Selection

The art of choosing the *right* prompt at runtime — not hardcoding a single template.

---

### Technique 1: Classified Parameter Routing

**What:** A router that classifies the incoming request (subject, difficulty, bloom level, question type) and selects the best-fit prompt template from a library.

**Why:** A single prompt cannot be optimal for every scenario. A Grade-3 "Remember" MCQ needs very different instructions than a Grade-12 "Evaluate" essay question. Routing lets you specialize prompts per use case without writing giant if-else chains.
>prompt ROUTING: based on quality score input (NEEDS llm)
		based on context of input CLASSIFICATION(NEEDS LLM)
		OTHERS NO IDES

TELL BEST PRACTISES/RESOURCES TO REACD THIS STUFF
**How it works:**

```
Input Request → Classify(subject, difficulty, bloom) → "bucket_key"
                                                            ↓
                                      Prompt Library ──→ Select template
                                                            ↓
                                                   Fill template with data → LLM
```

The classification can be:
1. **Rule-based** — simple mapping dict (fast, predictable)
2. **Embedding-based** — compare request embedding against template descriptions (flexible, handles edge cases)
3. **LLM-based** — ask a cheap model to pick the best template (most flexible, slowest)

We implement approach #1 (rule-based) with a fallback chain.

**Project code:** [`context_engineering/prompt_router.py → PromptRouter`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/prompt_router.py)

**Gotchas:**
- Too many buckets = maintenance nightmare. Start with 5-8 and split only when you measure quality differences.
- Always have a `"default"` fallback — unknown input combinations should never crash.

---

### Technique 2: Template-Data Separation

**What:** Separating the prompt *template* (the instructions, structure, persona) from the *data* (the actual values like subject name, context, examples) so they can evolve independently.

**Why:**
- You can A/B test templates without changing code
- Templates can be versioned (v1, v2) and rolled back
- Data validation (e.g., Pydantic) catches bad inputs before they hit the LLM
- Non-developers (curriculum experts) can edit templates

**How it works:**

```
Template File (Jinja2 / f-string):
  "Generate {num_questions} questions about {topic} at {difficulty} level..."

    +

Runtime Data (from API request):
  {"num_questions": 5, "topic": "Algebra", "difficulty": "Hard"}

    =

Final Prompt (assembled at call time)
```

**Before (hardcoded in mylang4.py):**
```python
self.question_template = """You are a highly skilled..."""  # 40-line string
```

**After (template loaded from config):**
```python
template = self.prompt_library.get_template("math", "hard")
prompt = template.render(data)
```

**Project code:** [`context_engineering/prompt_router.py → PromptLibrary`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/prompt_router.py)

**Gotchas:**
- Escaped curly braces `{{` in LangChain PromptTemplate — already a known issue in this project (see the `{{` in existing templates).
- Keep templates readable. If a template exceeds ~60 lines, split it into composable sections.

---

### Technique 3: Few-Shot Example Injection

**What:** Dynamically selecting 1-3 high-quality example Q&As from a bank and injecting them into the prompt to show the LLM "here's what a good output looks like."

**Why:**
- Few-shot examples are the strongest way to control output format and quality
- Different subjects need different example styles (math with equations vs. literature with passages)
- Dynamic selection > static examples because you can match the *exact* difficulty + bloom level

**How it works:**

```
Request: {subject: "Math", difficulty: "Hard", bloom: "Analyze"}
                    ↓
Few-Shot Bank (JSON file, subject-keyed):
  math.hard.analyze → [example1, example2, example3]
                    ↓
Select best 2 examples → inject into prompt as:
  "Here are examples of the quality expected:
   Example 1: ...
   Example 2: ..."
                    ↓
LLM sees concrete patterns → mimics format + quality
```

**Project code:**
- [`context_engineering/prompt_router.py → FewShotSelector`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/prompt_router.py)
- [`context_engineering/examples/few_shot_examples.json`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/examples/few_shot_examples.json)

**Gotchas:**
- Too many examples = wasted tokens + model may copy verbatim instead of generating novel questions.
- Examples must be *high quality*. Bad examples teach bad patterns.
- Keep examples fresh — rotate them periodically to avoid model "memorizing" a style.

---

## Family B: Context Compression

Techniques to reduce the volume of context while preserving its information value.

---

### Technique 4: Trimming (Token Truncation)

**What:** Cutting context to fit within a token budget. The key insight: *how* you cut matters enormously.

**Why:** LLM context windows are finite and expensive. Stuffing too much context degrades performance (the "lost in the middle" phenomenon) and increases cost/latency.

**Three trimming modes:**

| Mode | How | Best for |
|---|---|---|
| `hard_cutoff` | Cut at exact token count | Speed-critical paths |
| `sentence_boundary` | Cut at the nearest sentence end before the limit | Preserving meaning |
| `paragraph_boundary` | Cut at nearest paragraph break | Preserving structure |

```
Original (1500 tokens):
  "The quadratic formula is derived from completing the square.
   Given ax² + bx + c = 0, we can..."

hard_cutoff at 1000 tokens:
  "The quadratic formula is derived from completing the square.
   Given ax² + bx + c = 0, we ca"  ← broken mid-word!

sentence_boundary at 1000 tokens:
  "The quadratic formula is derived from completing the square."  ← clean cut
```

**Already existed in project:** [`mylang4.py → _truncate_to_tokens()`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/mylang4.py) (hard cutoff mode only)

**Enhanced version:** [`context_engineering/context_compressor.py → ContextTrimmer`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/context_compressor.py)

**Gotchas:**
- `tiktoken` model name must match your actual model. Using `"gpt-4"` encoding for a different model gives wrong token counts.
- Sentence splitting by `.` is naive — abbreviations like "Dr." or "U.S.A." create false splits. Use a proper sentence tokenizer for production.

---

### Technique 5: Summarization (Context Distillation)

**What:** Using a lightweight/cheap LLM call to compress long retrieved context into a focused, dense summary before passing it to the main (expensive) generation prompt.

**Why:**
- RAG retrieval often returns 5-10 chunks, many partially relevant. Summarization extracts only what matters.
- Reduces main prompt tokens by 80-90%.
- The summary can be *constrained* — "summarize only facts about {topic} at {difficulty} level" — acting as an intelligent filter.

**How it works:**

```
Retrieved chunks (2000 tokens):
  [chunk1: general intro to algebra]
  [chunk2: quadratic equations derivation]
  [chunk3: homework tips]
  [chunk4: quadratic applications]
                    ↓
Summarizer (cheap model, e.g., gpt-4o-mini):
  "Summarize these chunks focusing ONLY on quadratic equations
   at Hard difficulty for Grade 10 students"
                    ↓
Summary (300 tokens):
  "Quadratic equations take the form ax²+bx+c=0.
   Solutions found via factoring, completing the square,
   or the quadratic formula. Applications include..."
                    ↓
Main prompt uses this 300-token summary instead of 2000-token raw chunks
```

**Project code:** [`context_engineering/context_compressor.py → ContextSummarizer`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/context_compressor.py)

**Gotchas:**
- The summarizer LLM can hallucinate facts not in the original chunks. Always use `temperature=0` and a tight constraint prompt.
- Adds latency (one extra LLM call). Make it optional/configurable for time-sensitive paths.
- Don't summarize already-short context (< 500 tokens) — the overhead isn't worth it.

---

### Technique 6: Pruning (Quality Gating)

**What:** Removing low-value content from the context *before* it reaches the LLM. Unlike trimming (which cuts by size), pruning cuts by *quality/relevance*.

**Why:** Irrelevant context actively harms output quality — it's called "context poisoning." A chunk about homework tips injected into a question-generation prompt will confuse the model.

**Three pruning strategies:**

| Strategy | What it removes | When to use |
|---|---|---|
| `min_quality` | Chunks below a quality score threshold | Always (cheap, fast) |
| `relevance_gate` | Chunks below a relevance score to the query | When using RAG retrieval |
| `dedup` | Near-duplicate chunks (same content from different pages) | Multi-page PDF ingestion |

**Already existed in project:** [`mylang4.py → quality_score > 0.3` filter](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/mylang4.py) (min_quality only)

**Enhanced version:** [`context_engineering/context_compressor.py → ContextPruner`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/context_compressor.py)

**Gotchas:**
- Aggressive pruning can remove *all* context, leaving the LLM with nothing. Always check if result is empty and fall back to unpruned context.
- Dedup by exact match misses paraphrased duplicates. Use embedding cosine similarity for robust dedup.

---

## Family C: Context Placement

*Where* you put information in the prompt is as important as *what* you include.

---

### Technique 7: Strategic Ordering (Primacy/Recency Effect)

**What:** Deliberately arranging prompt sections so critical information sits at the **beginning** or **end** — never buried in the middle.

**Why:** Research shows LLMs attend to context in a U-shaped pattern:

```
Attention Level:
  HIGH ████████░░░░░░░░░░░░░████████ HIGH
       ↑ Beginning    Middle ↓      ↑ End
       (System prompt,       (Retrieved docs,
        persona)              examples, question)

  The middle = "lost in the middle" = lowest attention
```

**Optimal prompt structure:**

```
┌─────────────────────────────────┐
│ 🔴 HIGH ATTENTION ZONE (start) │  ← System instructions, persona, constraints
│                                 │
│ 🟡 LOW ATTENTION ZONE (middle) │  ← Background context, retrieved docs
│                                 │
│ 🔴 HIGH ATTENTION ZONE (end)   │  ← Few-shot examples, the actual question,
│                                 │     output format specification
└─────────────────────────────────┘
```

**Project code:** [`context_engineering/context_placer.py → ContextPlacer`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/context_placer.py)

**Gotchas:**
- This effect is model-dependent. GPT-4 shows it less than GPT-3.5, but it still exists.
- Don't over-optimize — clear, logical structure matters more than micro-positioning.

---

### Technique 8: Sliding Window + Anchoring

**What:** For multi-turn interactions (like the 3-attempt revision loop in this project), managing what stays, what gets summarized, and what gets dropped across turns.

**Why:** Each revision attempt adds more context (previous output + feedback). Without management, the 3rd attempt's prompt is 3× larger than the 1st, potentially exceeding token limits and degrading quality.

**How it works:**

```
Turn 1 (Attempt 1):
  [System Prompt] + [Context] + [Generate instructions]
  → Output: questions_v1
  → Feedback: "difficulty too low, missing bloom alignment"

Turn 2 (Attempt 2):
  [System Prompt]                          ← ANCHORED (always present)
  + [Context]                              ← ANCHORED
  + [Summarized: "v1 was rejected for:    ← SLIDING (summarized)
     low difficulty, bloom misalignment"]
  + [Revision instructions]                ← RECENT (full detail)

Turn 3 (Attempt 3):
  [System Prompt]                          ← ANCHORED
  + [Context]                              ← ANCHORED
  + [Summarized: "v1 and v2 rejected..."] ← SLIDING (further compressed)
  + [Latest feedback in full]              ← RECENT
```

**Three zones:**
- **Anchored** — never removed (system prompt, core constraints)
- **Sliding** — older turns get summarized/trimmed as new turns arrive
- **Recent** — latest turn always kept in full

**Project code:** [`context_engineering/context_placer.py → SlidingWindowManager`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/context_placer.py)

**Gotchas:**
- The feedback loop in `mylang4.py` only does 3 attempts, so the window is short. But the pattern generalizes to chatbots, agents, and any multi-turn system.
- Summarizing too aggressively between turns can lose *why* a previous attempt was rejected, causing the same mistake to repeat.

---

## Family D: Retrieval & Caching

Getting the right information efficiently.

---

### Technique 9: RAG with Reranking

**What:** After initial retrieval (vector similarity search), applying a second-pass ranker that scores documents more precisely against the query.

**Why:** Embedding similarity is fast but coarse. A document mentioning "quadratic" might rank high for a "linear equations" query because the embeddings are close in vector space. Reranking catches these false positives.

**Two-stage process:**

```
Query: "Generate hard questions on quadratic equations"
                    ↓
Stage 1 — Retrieval (FAISS, fast, returns top-k):
  [doc1: quadratic equations] score: 0.92
  [doc2: linear equations]    score: 0.88  ← false positive!
  [doc3: quadratic formula]   score: 0.85
  [doc4: polynomial basics]   score: 0.82
                    ↓
Stage 2 — Reranking (cross-encoder or custom scorer, precise):
  [doc1: quadratic equations] rerank: 0.95  ✅
  [doc3: quadratic formula]   rerank: 0.90  ✅
  [doc4: polynomial basics]   rerank: 0.60  ⚠️ borderline
  [doc2: linear equations]    rerank: 0.30  ❌ demoted!
```

**Already in project:** [`mylang4.py → _calculate_document_relevance()`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/mylang4.py) — this IS a simple reranker (keyword + metadata scoring).

**Future enhancement:** Replace with a cross-encoder model (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) for much better precision. Documented here as a learning reference; current project uses the lightweight keyword approach.

**Gotchas:**
- Cross-encoder reranking is slow (O(n) model calls vs O(1) vector search). Only rerank top-k, not the entire corpus.
- Reranking can't recover documents that weren't retrieved in Stage 1. If initial k is too small, good documents may be missed entirely.

---

### Technique 10: Semantic Caching

**What:** Caching LLM responses and matching new requests by *meaning* (embedding similarity) rather than exact string match.

**Why:**
- If a teacher generates "5 Hard MCQs on Quadratic Equations for Grade 10" and another generates "5 Difficult MCQ questions about Quadratic Equations, Class 10" — these are semantically identical. A semantic cache can serve the cached response for the second request.
- Saves LLM API costs and reduces latency dramatically.

**How it works:**

```
New request: "Generate 5 MCQs on algebra for Grade 8"
                    ↓
Embed the request → vector_new
                    ↓
Search cache for similar vectors:
  cache_entry_1: "5 MCQs algebra grade 8" → similarity: 0.97  ← HIT!
  cache_entry_2: "3 MCQs geometry grade 10" → similarity: 0.45
                    ↓
If similarity > threshold (e.g., 0.92):
  Return cached response (no LLM call!)
Else:
  Call LLM → cache the response with its embedding
```

**Project code:** [`context_engineering/context_cache.py → SemanticCache`](file:///d:/Github_Codes/Question_paper/Question_maker_feedback_loop/context_engineering/context_cache.py)

**Gotchas:**
- Similarity threshold is critical. Too low (0.80) = stale/wrong results. Too high (0.99) = cache never hits.
- Cache must be invalidated when prompts/templates change (a v2 prompt should not serve v1 cached results).
- For education, caching is tricky — teachers may want *different* questions each time even for the same topic. Add a `bypass_cache` flag.

---

## The Full Pipeline

When all 10 techniques are wired together, a single request flows through:

```
API Request
    ↓
┌─────────────────────────────────────────────────┐
│ 1. ROUTE    → Pick the best prompt template     │  (Technique 1)
│ 2. SEPARATE → Load template + fill with data    │  (Technique 2)
│ 3. RETRIEVE → RAG search for relevant context   │  (Technique 9)
│ 4. PRUNE    → Remove low-quality/irrelevant     │  (Technique 6)
│ 5. TRIM     → Cut to token budget               │  (Technique 4)
│ 6. SUMMARIZE→ Compress if still too long        │  (Technique 5)
│ 7. FEW-SHOT → Inject matching examples          │  (Technique 3)
│ 8. PLACE    → Order sections for max attention   │  (Technique 7)
│ 9. CACHE?   → Check semantic cache first        │  (Technique 10)
│10. WINDOW   → Manage revision history           │  (Technique 8)
└─────────────────────────────────────────────────┘
    ↓
LLM Call → Response → Verify → (Retry loop with sliding window)
```

---

## Key Failure Modes to Avoid

| Failure | What happens | Prevention |
|---|---|---|
| **Context Stuffing** | Too much context → "lost in the middle" → wrong answers | Techniques 4, 5, 6 |
| **Context Poisoning** | Irrelevant context → confused output | Technique 6 (pruning) |
| **Stale Context** | Outdated cached responses | Technique 10 (TTL + invalidation) |
| **Template Drift** | Template changes not tested → quality regression | Technique 2 (versioning) |
| **Example Contamination** | Bad few-shot examples → bad outputs | Technique 3 (curated bank) |

---

## Further Reading

- [Anthropic: Building Effective Agents](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering)
- [Lost in the Middle (Stanford, 2023)](https://arxiv.org/abs/2307.03172)
- [LLMLingua: Prompt Compression](https://arxiv.org/abs/2310.05736)
- [Context Engineering vs Prompt Engineering (2025)](https://sourcegraph.com/blog/context-engineering)
