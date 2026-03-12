"""LLM-based benchmark question generation and answer evaluation."""

import json
import logging
from typing import Any, Protocol

from .models import BenchmarkQuestion, Difficulty, QuestionCategory

logger = logging.getLogger(__name__)

QUESTION_GENERATION_PROMPT = """You are an expert examiner creating PhD-qualifying-exam-style questions.

Topic: {topic}

Available knowledge entities:
{entities}

Available claims:
{claims}

Generate {count} benchmark questions at the specified difficulty levels.
Each question should test a specific aspect of knowledge:
- factual_recall: Direct factual knowledge
- reasoning: Logical inference from known facts
- synthesis: Combining multiple pieces of knowledge
- application: Applying knowledge to novel scenarios

Difficulty distribution:
- phd: {phd_count} questions (require deep expertise, multi-step reasoning)
- masters: {masters_count} questions (require solid understanding)
- undergrad: {undergrad_count} questions (fundamental concepts)

Return a JSON array of objects with these fields:
- "question": the question text
- "difficulty": "phd" | "masters" | "undergrad"
- "expected_answer_keywords": list of 3-5 keywords that a correct answer must include
- "category": "factual_recall" | "reasoning" | "synthesis" | "application"

Return ONLY the JSON array, no other text."""


ANSWER_EVALUATION_PROMPT = """You are evaluating an answer against expected criteria.

Question: {question}
Expected answer keywords: {keywords}
Given answer: {answer}

Evaluate:
1. Does the answer address the question correctly?
2. Does it include the expected key concepts?
3. Rate confidence from 0.0 to 1.0.

Return JSON:
{{"correct": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}

Return ONLY the JSON object."""


class LLMClient(Protocol):
    """Protocol for LLM inference clients."""

    async def complete(self, prompt: str, model: str) -> str: ...


class QuestionGenerator:
    """Generates benchmark questions and evaluates answers using an LLM."""

    def __init__(self, llm_client: LLMClient, model: str = "gpt-4o-mini") -> None:
        self._llm = llm_client
        self._model = model

    async def generate_questions(
        self,
        topic: str,
        entities: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        count: int = 20,
    ) -> list[BenchmarkQuestion]:
        """Generate benchmark questions grounded in the topic's knowledge."""
        phd_count = max(1, int(count * 0.4))
        masters_count = max(1, int(count * 0.35))
        undergrad_count = max(1, count - phd_count - masters_count)

        entity_text = "\n".join(
            f"- {e.get('name', 'unknown')}: {e.get('description', '')[:100]}"
            for e in entities[:50]
        )
        claim_text = "\n".join(
            f"- {c.get('text', '')[:120]} (confidence: {c.get('confidence', 0):.2f})"
            for c in claims[:30]
        )

        prompt = QUESTION_GENERATION_PROMPT.format(
            topic=topic,
            entities=entity_text or "(no entities available)",
            claims=claim_text or "(no claims available)",
            count=count,
            phd_count=phd_count,
            masters_count=masters_count,
            undergrad_count=undergrad_count,
        )

        raw = await self._llm.complete(prompt, self._model)
        return self._parse_questions(topic, raw)

    def _parse_questions(
        self, topic: str, raw_response: str
    ) -> list[BenchmarkQuestion]:
        """Parse LLM response into BenchmarkQuestion objects."""
        try:
            text = raw_response.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            items = json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.error("Failed to parse question generation response")
            return []

        questions: list[BenchmarkQuestion] = []
        for item in items:
            try:
                q = BenchmarkQuestion(
                    topic=topic,
                    question=item["question"],
                    difficulty=Difficulty(item.get("difficulty", "undergrad")),
                    expected_answer_keywords=item.get(
                        "expected_answer_keywords", []
                    ),
                    category=QuestionCategory(
                        item.get("category", "factual_recall")
                    ),
                )
                questions.append(q)
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed question: %s", exc)
        return questions

    async def evaluate_answer(
        self,
        question: str,
        expected_keywords: list[str],
        answer: str,
    ) -> dict[str, Any]:
        """Use the LLM to evaluate an answer against expected keywords."""
        prompt = ANSWER_EVALUATION_PROMPT.format(
            question=question,
            keywords=", ".join(expected_keywords),
            answer=answer,
        )
        raw = await self._llm.complete(prompt, self._model)
        try:
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.error("Failed to parse answer evaluation response")
            return {"correct": False, "confidence": 0.0, "reasoning": "Parse error"}
