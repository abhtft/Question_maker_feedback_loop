"""
Context Engineering — Context Placer
======================================
Techniques 7, 8: Strategic Ordering and Sliding Window + Anchoring.

Learning notes:
  - Technique 7 (Strategic Ordering): LLMs attend to the BEGINNING and END
    of the context window much better than the middle. This is called the
    "lost in the middle" phenomenon (Stanford, 2023). The ContextPlacer
    arranges prompt sections to exploit this.
    
  - Technique 8 (Sliding Window): In multi-turn interactions (like the
    3-attempt revision loop in this project), the context grows with each
    turn. The SlidingWindowManager keeps critical info anchored, recent
    feedback in full, and older history compressed.
"""

import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Technique 7: Strategic Ordering — ContextPlacer
# ══════════════════════════════════════════════════════════════════════

class ContextPlacer:
    """
    Arranges the final prompt sections to maximize LLM attention on
    critical information.
    
    The "Lost in the Middle" principle:
    
        Attention: HIGH ████░░░░░░░░░░░░░████ HIGH
                        ↑ Start    Middle ↓   ↑ End
    
    Optimal layout:
    
    ┌─────────────────────────────────────────────┐
    │ 🔴 ZONE 1 (HIGH attention — start)         │
    │   • System persona / role                   │
    │   • Hard constraints ("must have 4 options")│
    │   • Topic + difficulty + bloom level        │
    ├─────────────────────────────────────────────┤
    │ 🟡 ZONE 2 (LOW attention — middle)         │
    │   • Retrieved context (study material)      │
    │   • Background information                  │
    │   • Revision history (if any)               │
    ├─────────────────────────────────────────────┤
    │ 🔴 ZONE 3 (HIGH attention — end)           │
    │   • Few-shot examples                       │
    │   • Output format specification             │
    │   • Rules (answer must match option, etc.)  │
    │   • The actual instruction ("Generate...")  │
    └─────────────────────────────────────────────┘
    
    Why this order?
      - Persona at the start sets the model's "mode" before it reads anything else
      - Context in the middle can be large but doesn't need exact recall
      - Format + rules at the end = last thing the model reads before generating
        → highest compliance
    """

    def assemble(self, template: str, context: str,
                 few_shot_examples: List[Dict[str, Any]],
                 topic_data: Dict[str, Any],
                 revision_history: str = '') -> str:
        """
        Assemble the final prompt with strategic section ordering.
        
        This method fills the template placeholders AND reorders sections
        for optimal attention distribution.
        
        Args:
            template: The prompt template body (from PromptRouter)
            context: Processed context (pruned, trimmed, summarized)
            few_shot_examples: List of example Q&A dicts
            topic_data: Original request data
            revision_history: Summarized revision history (from SlidingWindowManager)
            
        Returns:
            Fully assembled prompt string ready for LLM
        """
        # Format few-shot examples into a text block
        few_shot_section = self._format_few_shot_section(few_shot_examples)

        # Build the context section with revision history
        full_context = context
        if revision_history:
            full_context = (
                f"{context}\n\n"
                f"--- Previous Attempt Feedback ---\n"
                f"{revision_history}"
            )

        # Fill template placeholders
        # The template uses {variable} syntax (LangChain PromptTemplate style)
        try:
            assembled = template.format(
                num_questions=topic_data.get('numQuestions', 1),
                question_type=topic_data.get('questionType', 'MCQ'),
                subject=topic_data.get('subjectName', 'Unknown'),
                class_grade=topic_data.get('classGrade', 'Unknown'),
                topic=topic_data.get('sectionName', 'Unknown'),
                difficulty=topic_data.get('difficulty', 'Medium'),
                bloom_level=topic_data.get('bloomLevel', 'Remember'),
                context=full_context,
                instructions=topic_data.get('additionalInstructions', ''),
                few_shot_section=few_shot_section,
            )
        except KeyError as e:
            logger.error(f"Template placeholder not found: {e}. Using raw template.")
            assembled = template

        logger.info(f"Assembled prompt: {len(assembled)} chars, "
                     f"context={len(full_context)} chars, "
                     f"few_shot={len(few_shot_section)} chars")
        return assembled

    def _format_few_shot_section(self, examples: List[Dict[str, Any]]) -> str:
        """
        Format few-shot examples into a prompt-ready text block.
        
        Returns empty string if no examples are available.
        Placed near the END of the prompt (Zone 3) for maximum attention.
        """
        if not examples:
            return ""

        parts = ["--- Examples of expected output quality ---\n"]
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


# ══════════════════════════════════════════════════════════════════════
# Technique 8: Sliding Window + Anchoring — SlidingWindowManager
# ══════════════════════════════════════════════════════════════════════

class SlidingWindowManager:
    """
    Manages context across multiple revision attempts (turns) in the
    question generation feedback loop.
    
    The problem:
      In mylang4.py, if the first attempt is rejected by the verifier,
      the system retries up to 3 times. Each retry adds:
        - The previous output (rejected questions)
        - The verification feedback (what was wrong)
        - The improvement suggestions
      
      Without management, the 3rd attempt's prompt is MUCH larger than
      the 1st, potentially exceeding token limits and degrading quality.
    
    The solution — three zones:
    
    ┌──────────────────────────────────────────┐
    │ 🔒 ANCHORED (always present, never trimmed) │
    │   • System prompt                           │
    │   • Core context (study material)           │
    │   • Topic constraints                       │
    ├──────────────────────────────────────────┤
    │ 📜 SLIDING (compressed as new turns arrive) │
    │   • Older attempt feedback (summarized)     │
    ├──────────────────────────────────────────┤
    │ 🆕 RECENT (always kept in full)             │
    │   • Latest verification feedback            │
    │   • Latest improvement suggestions          │
    └──────────────────────────────────────────┘
    
    Example across 3 attempts:
    
    Attempt 1: [anchored] + [generate]
    Attempt 2: [anchored] + [summary of attempt 1 feedback] + [full attempt 1 feedback]
    Attempt 3: [anchored] + [summary of attempts 1+2 feedback] + [full attempt 2 feedback]
    
    Note: The "anchored" content is handled by the template itself.
    This class only manages the revision history (sliding + recent zones).
    """

    def __init__(self, max_history_chars: int = 500):
        """
        Args:
            max_history_chars: Maximum characters for the sliding zone
                (older history). Beyond this, older feedback is compressed
                to bullet points.
        """
        self.max_history_chars = max_history_chars
        self.history: List[Dict[str, Any]] = []

    def update(self, attempt: int, feedback: Dict[str, Any]) -> str:
        """
        Record a new attempt's feedback and return the formatted
        revision history string.
        
        Args:
            attempt: Current attempt number (1-based)
            feedback: Verification result dict from QuestionQualityVerifier
                Expected keys: 'overall_verdict', 'detailed_feedback',
                'specific_issues', 'improvement_suggestions'
                
        Returns:
            Formatted revision history string to inject into the prompt
        """
        # Add feedback to history
        self.history.append({
            'attempt': attempt,
            'verdict': feedback.get('overall_verdict', 'UNKNOWN'),
            'issues': feedback.get('specific_issues', []),
            'suggestions': feedback.get('improvement_suggestions', []),
            'scores': feedback.get('detailed_feedback', {}),
        })

        # Build the output: older history (summarized) + recent (full)
        return self._format_history()

    def _format_history(self) -> str:
        """
        Format the history into a prompt-ready string.
        
        Older entries → compressed to bullet points (sliding zone)
        Latest entry  → kept in full detail (recent zone)
        """
        if not self.history:
            return ""

        parts = []

        # ── Sliding zone: older entries (compressed) ──────────────────
        if len(self.history) > 1:
            older = self.history[:-1]
            summary_lines = []
            for entry in older:
                issues_brief = '; '.join(entry['issues'][:2])  # Keep only top 2 issues
                summary_lines.append(
                    f"• Attempt {entry['attempt']}: {entry['verdict']} — {issues_brief}"
                )

            summary = '\n'.join(summary_lines)

            # Trim if too long
            if len(summary) > self.max_history_chars:
                summary = summary[:self.max_history_chars] + '...'

            parts.append("Previous attempts summary:")
            parts.append(summary)
            parts.append("")

        # ── Recent zone: latest entry (full detail) ───────────────────
        latest = self.history[-1]
        parts.append(f"Most recent attempt ({latest['attempt']}) — {latest['verdict']}:")
        
        if latest['issues']:
            parts.append("Issues found:")
            for issue in latest['issues']:
                parts.append(f"  - {issue}")

        if latest['suggestions']:
            parts.append("Improvement suggestions:")
            for suggestion in latest['suggestions']:
                parts.append(f"  - {suggestion}")

        # Score breakdown
        scores = latest.get('scores', {})
        if scores:
            parts.append("Quality scores:")
            for metric, score in scores.items():
                if isinstance(score, (int, float)):
                    parts.append(f"  - {metric}: {score}/100")

        return '\n'.join(parts)

    def reset(self):
        """Clear all history (start a new generation session)."""
        self.history.clear()
        logger.debug("Sliding window history cleared")

    def get_attempt_count(self) -> int:
        """Return the number of attempts recorded."""
        return len(self.history)
