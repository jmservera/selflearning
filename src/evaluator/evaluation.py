"""Core evaluation engine for measuring expertise."""

import logging
import statistics
from datetime import datetime, timezone
from typing import Any

from .knowledge_client import KnowledgeClient
from .models import (
    CoverageMetric,
    EvaluationReport,
    ExpertiseScorecard,
    GapSeverity,
    KnowledgeGap,
    SelfTestResult,
)
from .question_generator import QuestionGenerator

logger = logging.getLogger(__name__)

DEFAULT_TAXONOMY_AREAS = [
    "core_concepts",
    "key_figures",
    "methodologies",
    "applications",
    "history",
    "current_research",
    "controversies",
    "related_fields",
]

_STOP_WORDS = frozenset({
    "what", "is", "the", "a", "an", "of", "in", "how", "does", "do",
    "are", "was", "were", "which", "when", "where", "why", "can", "and",
    "or", "for", "to", "with", "that", "this", "it", "be", "has", "have",
    "not", "on", "at", "by", "from", "as", "but", "if", "so", "than",
})


class EvaluationEngine:
    """Orchestrates the full evaluation pipeline for a topic."""

    def __init__(
        self,
        knowledge_client: KnowledgeClient,
        question_generator: QuestionGenerator,
        max_questions: int = 20,
    ) -> None:
        self._knowledge = knowledge_client
        self._qgen = question_generator
        self._max_questions = max_questions

    async def evaluate(self, topic: str) -> EvaluationReport:
        """Run a full evaluation cycle for a topic."""
        logger.info("Starting evaluation for topic '%s'", topic)

        entities = await self._knowledge.get_entities(topic)
        claims = await self._knowledge.get_claims(topic)
        relationships = await self._knowledge.get_relationships(topic)

        coverage = self._assess_taxonomy_coverage(entities, relationships)

        questions = await self._qgen.generate_questions(
            topic, entities, claims, count=self._max_questions
        )
        self_test_results = await self._run_self_test(
            topic, questions, entities, claims
        )

        confidence_dist = self._analyze_confidence_distribution(entities, claims)
        gaps = self._find_gaps(topic, coverage, self_test_results, confidence_dist)
        scorecard = self._calculate_scorecard(
            topic, coverage, self_test_results, confidence_dist, gaps
        )
        recommendations = self._generate_recommendations(gaps, scorecard, coverage)

        report = EvaluationReport(
            topic=topic,
            scorecard=scorecard,
            gaps=gaps,
            self_test_results=self_test_results,
            taxonomy_coverage=coverage,
            recommendations=recommendations,
        )
        logger.info(
            "Evaluation complete for '%s': overall_score=%.1f, gaps=%d",
            topic,
            scorecard.overall_score,
            len(gaps),
        )
        return report

    def _assess_taxonomy_coverage(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> list[CoverageMetric]:
        """Compare entities against expected taxonomy areas."""
        area_entities: dict[str, list[dict]] = {
            area: [] for area in DEFAULT_TAXONOMY_AREAS
        }

        for entity in entities:
            category = entity.get("category", "").lower()
            entity_type = entity.get("type", "").lower()
            matched = False
            for area in DEFAULT_TAXONOMY_AREAS:
                area_key = area.replace("_", " ")
                if area_key in category or area_key in entity_type or area in category:
                    area_entities[area].append(entity)
                    matched = True
                    break
            if not matched:
                if entity_type in ("person", "researcher", "scientist"):
                    area_entities["key_figures"].append(entity)
                elif entity_type in ("method", "technique", "algorithm"):
                    area_entities["methodologies"].append(entity)
                elif entity_type in ("concept", "definition", "term"):
                    area_entities["core_concepts"].append(entity)
                else:
                    area_entities["core_concepts"].append(entity)

        entity_ids_by_area: dict[str, set[str]] = {
            area: {e.get("id", "") for e in ents}
            for area, ents in area_entities.items()
        }
        area_rels: dict[str, int] = {area: 0 for area in DEFAULT_TAXONOMY_AREAS}
        for rel in relationships:
            src = rel.get("source_id", "")
            tgt = rel.get("target_id", "")
            for area, ids in entity_ids_by_area.items():
                if src in ids or tgt in ids:
                    area_rels[area] += 1

        metrics = []
        for area in DEFAULT_TAXONOMY_AREAS:
            ents = area_entities[area]
            confidences = [e.get("confidence", 0.5) for e in ents]
            avg_conf = statistics.mean(confidences) if confidences else 0.0
            metrics.append(
                CoverageMetric(
                    area=area,
                    entity_count=len(ents),
                    relationship_count=area_rels[area],
                    avg_confidence=round(avg_conf, 3),
                )
            )
        return metrics

    async def _run_self_test(
        self,
        topic: str,
        questions: list,
        entities: list[dict[str, Any]],
        claims: list[dict[str, Any]],
    ) -> list[SelfTestResult]:
        """Answer generated questions using only the knowledge graph."""
        results: list[SelfTestResult] = []
        for q in questions:
            answer = self._rag_answer(q.question, entities, claims)
            evaluation = await self._qgen.evaluate_answer(
                q.question, q.expected_answer_keywords, answer
            )
            results.append(
                SelfTestResult(
                    question_id=q.id,
                    answer=answer,
                    correct=evaluation.get("correct", False),
                    confidence=min(
                        1.0, max(0.0, evaluation.get("confidence", 0.0))
                    ),
                    reasoning=evaluation.get("reasoning", ""),
                )
            )
        return results

    def _rag_answer(
        self,
        question: str,
        entities: list[dict[str, Any]],
        claims: list[dict[str, Any]],
    ) -> str:
        """Simple keyword-based RAG: find relevant knowledge and compose an answer."""
        q_words = {w.strip("?.,!;:'\"()[]") for w in question.lower().split()}
        q_keywords = q_words - _STOP_WORDS

        scored_entities = []
        for e in entities:
            name = e.get("name", "").lower()
            desc = e.get("description", "").lower()
            text = f"{name} {desc}"
            score = sum(1 for kw in q_keywords if kw in text)
            if score > 0:
                scored_entities.append((score, e))
        scored_entities.sort(key=lambda x: x[0], reverse=True)

        scored_claims = []
        for c in claims:
            text = c.get("text", "").lower()
            score = sum(1 for kw in q_keywords if kw in text)
            if score > 0:
                scored_claims.append((score, c))
        scored_claims.sort(key=lambda x: x[0], reverse=True)

        parts = []
        for _, e in scored_entities[:3]:
            parts.append(f"{e.get('name', '')}: {e.get('description', '')}")
        for _, c in scored_claims[:3]:
            parts.append(c.get("text", ""))

        if not parts:
            return "Insufficient knowledge to answer this question."
        return " ".join(parts)

    def _analyze_confidence_distribution(
        self,
        entities: list[dict[str, Any]],
        claims: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Bucket confidence scores across all knowledge items."""
        buckets: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "very_low": 0}
        for item in entities + claims:
            conf = item.get("confidence", 0.5)
            if conf >= 0.8:
                buckets["high"] += 1
            elif conf >= 0.6:
                buckets["medium"] += 1
            elif conf >= 0.4:
                buckets["low"] += 1
            else:
                buckets["very_low"] += 1
        return buckets

    def _find_gaps(
        self,
        topic: str,
        coverage: list[CoverageMetric],
        self_test_results: list[SelfTestResult],
        confidence_dist: dict[str, int],
    ) -> list[KnowledgeGap]:
        """Find areas with thin coverage, low confidence, or missing relationships."""
        gaps: list[KnowledgeGap] = []

        for metric in coverage:
            if metric.entity_count == 0:
                gaps.append(
                    KnowledgeGap(
                        topic=topic,
                        area=metric.area,
                        severity=GapSeverity.CRITICAL,
                        description=f"No entities found for '{metric.area}'",
                        entity_count=0,
                        suggested_queries=[
                            f"{topic} {metric.area.replace('_', ' ')}",
                            f"overview of {metric.area.replace('_', ' ')} in {topic}",
                        ],
                    )
                )
            elif metric.entity_count < 3:
                gaps.append(
                    KnowledgeGap(
                        topic=topic,
                        area=metric.area,
                        severity=GapSeverity.MODERATE,
                        description=(
                            f"Only {metric.entity_count} entities for '{metric.area}'"
                        ),
                        entity_count=metric.entity_count,
                        suggested_queries=[
                            f"detailed {metric.area.replace('_', ' ')} in {topic}",
                        ],
                    )
                )
            elif metric.avg_confidence < 0.5:
                gaps.append(
                    KnowledgeGap(
                        topic=topic,
                        area=metric.area,
                        severity=GapSeverity.MODERATE,
                        description=(
                            f"Low confidence ({metric.avg_confidence:.2f}) "
                            f"in '{metric.area}'"
                        ),
                        entity_count=metric.entity_count,
                        suggested_queries=[
                            f"authoritative sources for "
                            f"{metric.area.replace('_', ' ')} in {topic}",
                        ],
                    )
                )

            if metric.relationship_count == 0 and metric.entity_count > 0:
                gaps.append(
                    KnowledgeGap(
                        topic=topic,
                        area=metric.area,
                        severity=GapSeverity.MINOR,
                        description=(
                            f"No relationships mapped for '{metric.area}'"
                        ),
                        entity_count=metric.entity_count,
                        suggested_queries=[
                            f"how {metric.area.replace('_', ' ')} "
                            f"connects to other areas in {topic}",
                        ],
                    )
                )

        # Self-test failure analysis
        if self_test_results:
            failed = [r for r in self_test_results if not r.correct]
            failure_rate = len(failed) / len(self_test_results)
            if failure_rate > 0.5:
                gaps.append(
                    KnowledgeGap(
                        topic=topic,
                        area="general_knowledge",
                        severity=GapSeverity.CRITICAL,
                        description=(
                            f"Failed {len(failed)}/{len(self_test_results)} "
                            f"self-test questions ({failure_rate:.0%})"
                        ),
                        suggested_queries=[f"comprehensive overview of {topic}"],
                    )
                )

        # Confidence distribution analysis
        total = sum(confidence_dist.values())
        if total > 0:
            low_pct = (
                confidence_dist.get("low", 0) + confidence_dist.get("very_low", 0)
            ) / total
            if low_pct > 0.4:
                gaps.append(
                    KnowledgeGap(
                        topic=topic,
                        area="confidence",
                        severity=GapSeverity.MODERATE,
                        description=f"{low_pct:.0%} of knowledge has low confidence",
                        suggested_queries=[
                            f"authoritative references for {topic}",
                            f"peer-reviewed sources on {topic}",
                        ],
                    )
                )

        return gaps

    def _calculate_scorecard(
        self,
        topic: str,
        coverage: list[CoverageMetric],
        self_test_results: list[SelfTestResult],
        confidence_dist: dict[str, int],
        gaps: list[KnowledgeGap],
    ) -> ExpertiseScorecard:
        """Combine all metrics into a 0-100 overall score with subscores."""
        covered_areas = sum(1 for m in coverage if m.entity_count >= 3)
        coverage_score = (covered_areas / len(coverage) * 100) if coverage else 0.0

        entity_counts = [m.entity_count for m in coverage if m.entity_count > 0]
        avg_entities = statistics.mean(entity_counts) if entity_counts else 0
        depth_score = min(100.0, avg_entities / 10 * 100)

        if self_test_results:
            correct = sum(1 for r in self_test_results if r.correct)
            accuracy_score = correct / len(self_test_results) * 100
        else:
            accuracy_score = 0.0

        total_items = sum(confidence_dist.values())
        if total_items > 0:
            high_pct = confidence_dist.get("high", 0) / total_items
            med_pct = confidence_dist.get("medium", 0) / total_items
            recency_score = min(100.0, (high_pct * 100 + med_pct * 60))
        else:
            recency_score = 0.0

        overall_score = (
            coverage_score * 0.25
            + depth_score * 0.20
            + accuracy_score * 0.35
            + recency_score * 0.20
        )

        return ExpertiseScorecard(
            topic=topic,
            overall_score=round(overall_score, 1),
            coverage_score=round(coverage_score, 1),
            depth_score=round(depth_score, 1),
            accuracy_score=round(accuracy_score, 1),
            recency_score=round(recency_score, 1),
            confidence_distribution=confidence_dist,
            gap_count=len(gaps),
            evaluated_at=datetime.now(timezone.utc),
        )

    def _generate_recommendations(
        self,
        gaps: list[KnowledgeGap],
        scorecard: ExpertiseScorecard,
        coverage: list[CoverageMetric],
    ) -> list[str]:
        """Generate actionable recommendations from the evaluation."""
        recs: list[str] = []

        critical = [g for g in gaps if g.severity == GapSeverity.CRITICAL]
        for gap in critical:
            recs.append(
                f"URGENT: Address critical gap in '{gap.area}' — {gap.description}"
            )

        if scorecard.coverage_score < 50:
            empty_areas = [m.area for m in coverage if m.entity_count == 0]
            if empty_areas:
                recs.append(
                    f"Expand knowledge coverage. "
                    f"Missing areas: {', '.join(empty_areas[:3])}"
                )

        if scorecard.accuracy_score < 70:
            recs.append(
                "Improve knowledge accuracy. Consider re-scraping authoritative "
                "sources and cross-referencing claims."
            )

        if scorecard.depth_score < 50:
            recs.append(
                "Increase knowledge depth. Add more entities and relationships "
                "per topic area."
            )

        if scorecard.recency_score < 50:
            recs.append(
                "Refresh knowledge from recent sources. "
                "Many claims have low confidence."
            )

        if not recs:
            recs.append(
                "Knowledge quality is satisfactory. "
                "Continue regular learning cycles."
            )

        return recs
