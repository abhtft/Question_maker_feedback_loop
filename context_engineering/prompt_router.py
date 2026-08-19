"""
Context Engineering — Prompt Router
====================================
Techniques 1, 2, 3: Classified Parameter Routing, Template-Data Separation,
and Few-Shot Example Injection.

Learning notes:
  - Technique 1 (Routing): The PromptRouter classifies incoming request params
    and picks the best template from a library. Think of it like a switch-case
    on steroids — but declarative and extensible.
    
  - Technique 2 (Separation): PromptLibrary stores templates as data (not code).
    This means you can version them, A/B test them, and swap them without
    touching the generation logic.
    
  - Technique 3 (Few-Shot): FewShotSelector dynamically picks example Q&As
    from a JSON bank, matching the request's subject + difficulty + bloom level.
    These examples are injected into the prompt so the LLM sees concrete patterns.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Technique 2: Template-Data Separation — PromptLibrary
# ══════════════════════════════════════════════════════════════════════

class PromptLibrary:
    """
    Stores and retrieves prompt templates, keyed by (subject_group, difficulty_tier).
    
    Why separate templates from code?
      1. You can edit/add templates without modifying Python
      2. Templates are versionable (keep v1, v2 side by side)
      3. Domain experts (teachers) can contribute templates without coding
      4. A/B testing becomes trivial: just route 50% to template_v1, 50% to template_v2
    
    The templates use Python f-string style placeholders: {variable_name}
    These are filled at runtime by LangChain's PromptTemplate.
    """

    def __init__(self):
        # ── Subject-group templates ──────────────────────────────────
        # Each template is specialized for a subject family + difficulty tier.
        # Notice how math templates emphasize "show working" while 
        # literature templates emphasize "passage comprehension."
        
        self.templates = {
            # ── DEFAULT (catch-all) ──────────────────────────────────
            "default": {
                "system": "You are a highly skilled educational question generator.",
                "body": """Generate exactly {num_questions} {question_type} questions for:
Subject: {subject}
Grade: {class_grade}
Topic: {topic}
Difficulty: {difficulty}
Bloom's Level: {bloom_level}

Context:
{context}

{few_shot_section}

Additional Instructions:
{instructions}

Output Format (Strict JSON):
{{
  "questions": [
    {{
      "question": "Your question text here.",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option here",
      "explanation": "Detailed explanation with reasoning."
    }}
  ]
}}

Rules:
- Each question must have exactly 4 options.
- The answer must match one of the options exactly.
- The explanation must justify why the answer is correct.
- No extra text outside JSON.
- Output must not be in backticks."""
            },

            # ── MATHEMATICS (specialized) ─────────────────────────────
            "math_easy": {
                "system": "You are a mathematics teacher creating simple, confidence-building questions for young learners.",
                "body": """Generate exactly {num_questions} {question_type} questions for:
Subject: {subject}
Grade: {class_grade}
Topic: {topic}
Difficulty: Easy — use straightforward calculations, no multi-step problems
Bloom's Level: {bloom_level}

Context from study material:
{context}

{few_shot_section}

Additional Instructions:
{instructions}
- Use simple numbers (single/double digit where possible)
- Avoid word problems with complex scenarios
- Each option should be a plausible answer (no obviously wrong distractors)

Output Format (Strict JSON):
{{
  "questions": [
    {{
      "question": "Your question text here.",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option here",
      "explanation": "Show the step-by-step working to arrive at the answer."
    }}
  ]
}}

Rules:
- Each question must have exactly 4 options.
- The answer must match one of the options exactly.
- The explanation MUST show step-by-step working.
- No extra text outside JSON.
- Output must not be in backticks."""
            },

            "math_hard": {
                "system": "You are a senior mathematics examiner creating challenging questions that test deep conceptual understanding and multi-step problem solving.",
                "body": """Generate exactly {num_questions} {question_type} questions for:
Subject: {subject}
Grade: {class_grade}
Topic: {topic}
Difficulty: Hard — require multi-step reasoning, formula application, and conceptual understanding
Bloom's Level: {bloom_level}

Context from study material:
{context}

{few_shot_section}

Additional Instructions:
{instructions}
- Questions should require applying formulas or theorems, not just recall
- Distractors should represent common mistakes students make
- Include questions that test edge cases or boundary conditions where applicable

Output Format (Strict JSON):
{{
  "questions": [
    {{
      "question": "Your question text here.",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option here",
      "explanation": "Detailed step-by-step solution showing all mathematical working and the reasoning behind each step."
    }}
  ]
}}

Rules:
- Each question must have exactly 4 options.
- The answer must match one of the options exactly.
- The explanation MUST include full mathematical working.
- No extra text outside JSON.
- Output must not be in backticks."""
            },

            # ── SCIENCE (specialized) ─────────────────────────────────
            "science_easy": {
                "system": "You are a science teacher creating engaging, curiosity-sparking questions that test factual recall and basic understanding.",
                "body": """Generate exactly {num_questions} {question_type} questions for:
Subject: {subject}
Grade: {class_grade}
Topic: {topic}
Difficulty: Easy — test factual knowledge and basic definitions
Bloom's Level: {bloom_level}

Context from study material:
{context}

{few_shot_section}

Additional Instructions:
{instructions}
- Use clear, simple language appropriate for the grade level
- Relate questions to everyday observations where possible
- Distractors should be plausible but clearly wrong on reflection

Output Format (Strict JSON):
{{
  "questions": [
    {{
      "question": "Your question text here.",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option here",
      "explanation": "Explain the science behind the correct answer in simple terms."
    }}
  ]
}}

Rules:
- Each question must have exactly 4 options.
- The answer must match one of the options exactly.
- Explanations should connect to real-world phenomena.
- No extra text outside JSON.
- Output must not be in backticks."""
            },

            "science_hard": {
                "system": "You are a science examiner creating questions that test analytical thinking, experimental reasoning, and the ability to apply scientific principles to novel situations.",
                "body": """Generate exactly {num_questions} {question_type} questions for:
Subject: {subject}
Grade: {class_grade}
Topic: {topic}
Difficulty: Hard — require application of scientific principles to unfamiliar scenarios
Bloom's Level: {bloom_level}

Context from study material:
{context}

{few_shot_section}

Additional Instructions:
{instructions}
- Include scenario-based questions (experiments, data interpretation)
- Test cause-and-effect reasoning
- Distractors should represent common scientific misconceptions

Output Format (Strict JSON):
{{
  "questions": [
    {{
      "question": "Your question text here.",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option here",
      "explanation": "Explain the scientific principle involved, why the answer is correct, and why common misconceptions lead to wrong options."
    }}
  ]
}}

Rules:
- Each question must have exactly 4 options.
- The answer must match one of the options exactly.
- Explanations should address why wrong options are wrong.
- No extra text outside JSON.
- Output must not be in backticks."""
            },

            # ── LITERATURE / ENGLISH (specialized) ────────────────────
            "literature_default": {
                "system": "You are an English literature and language arts teacher creating questions that test comprehension, analysis, and appreciation of language.",
                "body": """Generate exactly {num_questions} {question_type} questions for:
Subject: {subject}
Grade: {class_grade}
Topic: {topic}
Difficulty: {difficulty}
Bloom's Level: {bloom_level}

Context from study material:
{context}

{few_shot_section}

Additional Instructions:
{instructions}
- For comprehension questions, ensure answers can be inferred from the context
- For grammar questions, provide clear and unambiguous examples
- For literary analysis, test understanding of devices and themes

Output Format (Strict JSON):
{{
  "questions": [
    {{
      "question": "Your question text here.",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "Correct option here",
      "explanation": "Explain with reference to the text, grammar rule, or literary device."
    }}
  ]
}}

Rules:
- Each question must have exactly 4 options.
- The answer must match one of the options exactly.
- The explanation should cite specific evidence or rules.
- No extra text outside JSON.
- Output must not be in backticks."""
            },
        }

        logger.info(f"PromptLibrary initialized with {len(self.templates)} templates: "
                     f"{list(self.templates.keys())}")

    def get_template(self, key: str) -> Dict[str, str]:
        """
        Retrieve a template by key. Falls back to 'default' if key not found.
        
        Returns:
            dict with 'system' (persona) and 'body' (main template) keys
        """
        template = self.templates.get(key, self.templates["default"])
        if key not in self.templates:
            logger.warning(f"Template '{key}' not found, using 'default'")
        return template

    def list_templates(self) -> List[str]:
        """List all available template keys."""
        return list(self.templates.keys())


# ══════════════════════════════════════════════════════════════════════
# Technique 1: Classified Parameter Routing — PromptRouter
# ══════════════════════════════════════════════════════════════════════

class PromptRouter:
    """
    Classifies request parameters into a "route key" and selects the
    corresponding prompt template from the PromptLibrary.
    
    Routing logic:
      1. Classify subject into a subject_group (math, science, literature, etc.)
      2. Classify difficulty into a tier (easy, medium/default, hard)
      3. Combine: "{subject_group}_{difficulty_tier}"
      4. Look up in PromptLibrary, fall back to "{subject_group}_default",
         then to "default"
    
    Why a router instead of a big if-else?
      - Declarative: routing rules are data, not code
      - Extensible: adding a new subject = adding to the mapping dict
      - Observable: you can log which route was taken per request
      - Testable: unit test the classification separately from the template
    """

    # ── Subject classification mapping ────────────────────────────────
    # Maps subject names (lowercase) to subject groups.
    # Add new subjects here — no code changes needed.
    SUBJECT_GROUPS = {
        # Mathematics family
        'mathematics': 'math', 'math': 'math', 'algebra': 'math',
        'geometry': 'math', 'trigonometry': 'math', 'calculus': 'math',
        'arithmetic': 'math', 'statistics': 'math',
        
        # Science family
        'science': 'science', 'physics': 'science', 'chemistry': 'science',
        'biology': 'science', 'environmental science': 'science',
        
        # Literature / English family
        'english': 'literature', 'literature': 'literature',
        'language arts': 'literature', 'grammar': 'literature',
        'hindi': 'literature',
        
        # History family
        'history': 'history', 'civics': 'history',
        'political science': 'history',
        
        # Geography family
        'geography': 'geography', 'earth science': 'geography',
    }

    # ── Difficulty tier mapping ───────────────────────────────────────
    DIFFICULTY_TIERS = {
        'easy': 'easy', 'simple': 'easy', 'basic': 'easy',
        'medium': 'default', 'moderate': 'default', 'intermediate': 'default',
        'hard': 'hard', 'difficult': 'hard', 'advanced': 'hard',
        'challenging': 'hard',
    }

    def __init__(self, library: PromptLibrary):
        self.library = library
        self.last_route_key = None  # For observability / logging

    def _classify_subject(self, subject: str) -> str:
        """Classify a subject name into a subject group."""
        subject_lower = subject.lower().strip()
        
        # Direct match
        if subject_lower in self.SUBJECT_GROUPS:
            return self.SUBJECT_GROUPS[subject_lower]
        
        # Partial match (e.g., "Advanced Mathematics" → "math")
        for key, group in self.SUBJECT_GROUPS.items():
            if key in subject_lower:
                return group
        
        return 'default'

    def _classify_difficulty(self, difficulty: str) -> str:
        """Classify a difficulty level into a tier."""
        difficulty_lower = difficulty.lower().strip()
        return self.DIFFICULTY_TIERS.get(difficulty_lower, 'default')

    def select_template(self, subject: str, difficulty: str,
                        bloom_level: str = '', question_type: str = 'MCQ') -> str:
        """
        Route the request to the best prompt template.
        
        Fallback chain:
          1. "{subject_group}_{difficulty_tier}" (e.g., "math_hard")
          2. "{subject_group}_default" (e.g., "math_default")
          3. "default"
        
        Args:
            subject: Subject name (e.g., "Mathematics", "Physics")
            difficulty: Difficulty level (e.g., "Easy", "Hard")
            bloom_level: Bloom's taxonomy level (for future fine-grained routing)
            question_type: Question type (for future fine-grained routing)
            
        Returns:
            The template body string (ready for placeholder filling)
        """
        subject_group = self._classify_subject(subject)
        difficulty_tier = self._classify_difficulty(difficulty)

        # Build route key with fallback chain
        primary_key = f"{subject_group}_{difficulty_tier}"
        fallback_key = f"{subject_group}_default"

        for key in [primary_key, fallback_key, "default"]:
            template = self.library.templates.get(key)
            if template:
                self.last_route_key = key
                logger.info(f"Route: subject='{subject}' → group='{subject_group}', "
                             f"difficulty='{difficulty}' → tier='{difficulty_tier}', "
                             f"routed to template='{key}'")
                return template["body"]

        # Should never reach here (default always exists), but just in case
        self.last_route_key = "default"
        return self.library.get_template("default")["body"]

    def get_system_prompt(self, subject: str, difficulty: str) -> str:
        """Get the system/persona prompt for the routed template."""
        subject_group = self._classify_subject(subject)
        difficulty_tier = self._classify_difficulty(difficulty)

        for key in [f"{subject_group}_{difficulty_tier}",
                     f"{subject_group}_default", "default"]:
            template = self.library.templates.get(key)
            if template:
                return template.get("system", "You are a highly skilled educational question generator.")

        return "You are a highly skilled educational question generator."


# ══════════════════════════════════════════════════════════════════════
# Technique 3: Few-Shot Example Injection — FewShotSelector
# ══════════════════════════════════════════════════════════════════════

class FewShotSelector:
    """
    Selects the best-matching few-shot examples from a subject-wise bank
    and formats them for injection into the prompt.
    
    Selection strategy:
      1. Filter by subject
      2. Filter by question_type (MCQ, etc.)
      3. Score remaining examples by how well they match the requested
         difficulty and bloom_level
      4. Return top N examples
    
    Why dynamic selection (not static examples)?
      - A "Hard + Analyze" request needs different examples than "Easy + Remember"
      - Rotating examples prevents the LLM from memorizing and copying patterns
      - Subject-specific examples teach subject-specific formatting conventions
    """

    def __init__(self, examples_path: str = None):
        """Load the few-shot example bank from JSON."""
        if examples_path is None:
            # Default: look next to this file
            examples_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'examples', 'few_shot_examples.json'
            )

        try:
            with open(examples_path, 'r', encoding='utf-8') as f:
                self.example_bank = json.load(f)
            logger.info(f"FewShotSelector loaded {sum(len(v.get('MCQ', [])) for v in self.example_bank.values())} "
                         f"examples across {len(self.example_bank)} subjects")
        except FileNotFoundError:
            logger.warning(f"Few-shot examples file not found at {examples_path}. "
                           f"FewShotSelector will return empty examples.")
            self.example_bank = {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse few-shot examples JSON: {e}")
            self.example_bank = {}

    def _match_subject(self, subject: str) -> str:
        """Map a subject name to a key in the example bank."""
        subject_lower = subject.lower().strip()
        
        # Direct match
        if subject_lower in self.example_bank:
            return subject_lower
        
        # Partial match
        subject_mappings = {
            'math': 'mathematics', 'algebra': 'mathematics', 'geometry': 'mathematics',
            'physics': 'science', 'chemistry': 'science', 'biology': 'science',
            'english': 'english', 'literature': 'english', 'grammar': 'english',
        }
        
        for key, bank_key in subject_mappings.items():
            if key in subject_lower and bank_key in self.example_bank:
                return bank_key
        
        return None

    def _score_example(self, example: dict, target_difficulty: str,
                       target_bloom: str) -> float:
        """
        Score how well an example matches the requested difficulty and bloom level.
        Higher score = better match.
        """
        score = 0.0
        
        # Difficulty match (most important)
        if example.get('difficulty', '').lower() == target_difficulty.lower():
            score += 0.6
        elif self._difficulty_distance(example.get('difficulty', ''), target_difficulty) <= 1:
            score += 0.3  # Adjacent difficulty is still useful

        # Bloom level match
        if example.get('bloom_level', '').lower() == target_bloom.lower():
            score += 0.4
        elif self._bloom_distance(example.get('bloom_level', ''), target_bloom) <= 1:
            score += 0.2  # Adjacent bloom level is still useful

        return score

    def _difficulty_distance(self, d1: str, d2: str) -> int:
        """Distance between two difficulty levels on a 1D scale."""
        scale = {'easy': 0, 'medium': 1, 'hard': 2}
        pos1 = scale.get(d1.lower(), 1)
        pos2 = scale.get(d2.lower(), 1)
        return abs(pos1 - pos2)

    def _bloom_distance(self, b1: str, b2: str) -> int:
        """Distance between two Bloom's levels on the taxonomy scale."""
        scale = {
            'remember': 0, 'understand': 1, 'apply': 2,
            'analyze': 3, 'evaluate': 4, 'create': 5
        }
        pos1 = scale.get(b1.lower(), 0)
        pos2 = scale.get(b2.lower(), 0)
        return abs(pos1 - pos2)

    def select(self, subject: str, difficulty: str, bloom_level: str,
               question_type: str = 'MCQ', count: int = 2) -> List[Dict[str, Any]]:
        """
        Select the best-matching few-shot examples.
        
        Args:
            subject: Subject name
            difficulty: Target difficulty level
            bloom_level: Target Bloom's taxonomy level
            question_type: Question type (MCQ, etc.)
            count: Number of examples to return
            
        Returns:
            List of example dicts, each with 'question', 'options', 'answer', 'explanation'
        """
        bank_key = self._match_subject(subject)
        if not bank_key:
            logger.info(f"No few-shot examples available for subject: {subject}")
            return []

        # Get examples for the question type
        examples = self.example_bank.get(bank_key, {}).get(question_type, [])
        if not examples:
            logger.info(f"No {question_type} examples for {bank_key}")
            return []

        # Score and sort
        scored = [(self._score_example(ex, difficulty, bloom_level), ex) for ex in examples]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Return top N examples (just the example content, not the metadata)
        selected = [item[1]['example'] for item in scored[:count]]
        logger.info(f"Selected {len(selected)} few-shot examples for "
                     f"{subject}/{difficulty}/{bloom_level}")
        return selected

    def format_for_prompt(self, examples: List[Dict[str, Any]]) -> str:
        """
        Format selected examples into a string block for prompt injection.
        
        Returns an empty string if no examples are available.
        """
        if not examples:
            return ""

        parts = ["Here are examples of the quality and format expected:\n"]
        for i, ex in enumerate(examples, 1):
            parts.append(f"Example {i}:")
            parts.append(f"  Question: {ex.get('question', '')}")
            options = ex.get('options', [])
            for j, opt in enumerate(options):
                parts.append(f"  {chr(65+j)}. {opt}")
            parts.append(f"  Answer: {ex.get('answer', '')}")
            parts.append(f"  Explanation: {ex.get('explanation', '')}")
            parts.append("")

        return "\n".join(parts)
