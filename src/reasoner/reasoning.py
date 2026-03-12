"""Core reasoning engine — RAG, gap analysis, contradiction resolution, synthesis.

Implements four reasoning strategies:

1. **Gap analysis** — identify topics with thin coverage or low confidence.
2. **Contradiction resolution** — weigh conflicting claims by authority/recency.
3. **Synthesis** — combine atomic knowledge into higher-order insights.
4. **Depth probe** — find areas that warrant deeper investigation.

All strategies follow the RAG pattern: retrieve relevant context from the
Knowledge service, augment the prompt, then reason with GPT-4o.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from opentelemetry import trace

from config import ReasonerConfig
from llm_client import LLMClient
from models import (
    ContradictionResolution,
    Insight,
    KnowledgeGap,
    ReasoningMeta,
    ReasoningRequest,
    ReasoningResult,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("reasoner.engine")

# ======================================================================
# Reasoning prompts — detailed, chain-of-thought
# ======================================================================

GAP_ANALYSIS_SYSTEM_PROMPT = """\
You are an expert research analyst evaluating the completeness of a knowledge
base on a specific topic.  Your job is to identify areas where knowledge is
thin, missing, contradictory, or low-confidence.

## Process (chain-of-thought)
1. Review the provided entities, claims, and relationships.
2. Identify categories or sub-topics that SHOULD be covered but are not.
3. Flag areas where confidence scores are consistently low.
4. Note any entities that are mentioned but never defined or described.
5. Suggest concrete search queries that would fill each gap.

## Severity levels
- **critical**: Core aspect of the topic is missing or has only low-confidence claims.
- **moderate**: Important sub-topic has thin coverage (few entities/claims).
- **minor**: Nice-to-have context is absent.

## Output format — ONLY valid JSON
{
  "gaps": [
    {
      "area": "name of the knowledge gap area",
      "severity": "critical|moderate|minor",
      "description": "why this is a gap and what's missing",
      "suggested_queries": ["search query 1", "search query 2"]
    }
  ],
  "reasoning": "step-by-step explanation of how you identified these gaps"
}

## Example
Topic: "Transformer Architecture"
Entities: ["Transformer", "Self-Attention", "BERT"]
Claims: [{"statement": "Transformers use self-attention", "confidence": 0.95}]

Output:
{
  "gaps": [
    {"area": "Training methodology", "severity": "critical", "description": "No information about how Transformers are trained (pre-training objectives, datasets, compute requirements)", "suggested_queries": ["Transformer pre-training methodology", "self-supervised learning for Transformers"]},
    {"area": "Decoder-only variants", "severity": "moderate", "description": "Only encoder models (BERT) mentioned. No coverage of GPT-style decoder-only architectures", "suggested_queries": ["GPT architecture decoder-only Transformer", "autoregressive language models"]},
    {"area": "Computational complexity", "severity": "minor", "description": "No discussion of O(n²) attention complexity or efficient attention variants", "suggested_queries": ["Transformer attention computational complexity", "efficient attention mechanisms linear"]}
  ],
  "reasoning": "The knowledge base covers the basic architecture (Transformer, Self-Attention) and one encoder variant (BERT), but is missing training methodology (critical for understanding), decoder-only models (major architecture family), and complexity analysis (practical consideration)."
}
"""

CONTRADICTION_SYSTEM_PROMPT = """\
You are an expert analyst specializing in evaluating conflicting information.
Given a set of claims about a topic, identify contradictions and determine
the most likely truth.

## Process (chain-of-thought)
1. Group claims by sub-topic.
2. Identify pairs or groups of claims that contradict each other.
3. For each contradiction:
   a. Compare confidence scores.
   b. Evaluate the quality of supporting evidence.
   c. Consider which claim is more specific vs. more general.
   d. Determine the most likely resolution.
4. Assign a confidence to your resolution.

## Rules
- Be explicit about your reasoning.
- If evidence is insufficient to resolve a contradiction, say so.
- Higher confidence + more evidence = more weight, but specificity matters.
- A single high-quality primary source may outweigh multiple secondary sources.

## Output format — ONLY valid JSON
{
  "resolutions": [
    {
      "claim_ids": ["id1", "id2"],
      "conflicting_statements": ["claim 1 text", "claim 2 text"],
      "resolution": "which claim is more likely correct and why",
      "confidence": 0.75,
      "reasoning": "step-by-step reasoning"
    }
  ],
  "summary": "overall assessment of contradiction patterns"
}

## Example
Claims:
- Claim A (confidence 0.85): "BERT has 110M parameters"
- Claim B (confidence 0.70): "BERT has 340M parameters"

Output:
{
  "resolutions": [
    {
      "claim_ids": ["id_a", "id_b"],
      "conflicting_statements": ["BERT has 110M parameters", "BERT has 340M parameters"],
      "resolution": "Both claims are correct — they refer to different BERT variants. BERT-base has 110M parameters and BERT-large has 340M parameters. The claims are not truly contradictory but lack specificity.",
      "confidence": 0.90,
      "reasoning": "BERT was released in two sizes. Claim A likely refers to BERT-base (110M) and Claim B to BERT-large (340M). Both are well-documented in the original paper. The contradiction is apparent rather than real."
    }
  ],
  "summary": "One apparent contradiction resolved — claims referred to different model variants."
}
"""

SYNTHESIS_SYSTEM_PROMPT = """\
You are an expert knowledge synthesizer.  Given entities, relationships, and
claims about a topic, generate higher-order insights that connect disparate
pieces of knowledge.

## Process (chain-of-thought)
1. Map the knowledge landscape — what domains and sub-topics are covered.
2. Identify cross-cutting themes that span multiple entities/claims.
3. Look for emergent patterns: trends, cause-effect chains, hierarchies.
4. Generate novel insights that are NOT explicitly stated but follow logically
   from the evidence.
5. Rate confidence for each insight.

## Insight quality criteria
- Must be grounded in the provided evidence (cite entity names).
- Must add value beyond simple restatement.
- Should connect at least 2 entities or claims.
- Confidence reflects how strongly the evidence supports the insight.

## Output format — ONLY valid JSON
{
  "insights": [
    {
      "statement": "the insight as a clear assertion",
      "supporting_entities": ["Entity1", "Entity2"],
      "confidence": 0.80,
      "reasoning_chain": "step-by-step reasoning that led to this insight"
    }
  ],
  "meta_observation": "high-level observation about the topic's knowledge structure"
}

## Example
Topic: "Large Language Models"
Entities: ["GPT-4", "BERT", "Transformer", "Self-Attention", "Scaling Laws"]
Claims: ["GPT-4 uses Transformer architecture", "Scaling laws predict model performance"]

Output:
{
  "insights": [
    {"statement": "The evolution from BERT to GPT-4 demonstrates a fundamental shift from task-specific fine-tuning to general-purpose capabilities enabled by scale", "supporting_entities": ["GPT-4", "BERT", "Scaling Laws"], "confidence": 0.85, "reasoning_chain": "BERT was designed for fine-tuning on specific tasks. GPT-4 is a general-purpose model. Scaling laws explain why larger models develop emergent capabilities without task-specific training."},
    {"statement": "Self-Attention is the critical shared component that enabled both the BERT and GPT families, making it the foundational innovation of modern NLP", "supporting_entities": ["Self-Attention", "BERT", "GPT-4", "Transformer"], "confidence": 0.90, "reasoning_chain": "Both BERT and GPT-4 are based on the Transformer architecture. Self-Attention is the core mechanism of Transformers. Without self-attention, neither architecture family would exist in its current form."}
  ],
  "meta_observation": "The knowledge base captures the architectural lineage of LLMs well but lacks coverage of practical deployment challenges and societal implications."
}
"""

DEPTH_PROBE_SYSTEM_PROMPT = """\
You are an expert research strategist.  Given a topic and its current knowledge
coverage, identify specific areas that warrant deeper investigation.

## Process
1. Assess the depth of coverage for each sub-topic.
2. Identify "shallow" areas — topics mentioned but not explored.
3. Identify "frontier" areas — cutting-edge developments that need tracking.
4. Prioritize by impact (what would most improve understanding).
5. Generate specific, actionable research queries.

## Output format — ONLY valid JSON
{
  "probes": [
    {
      "area": "area to investigate deeper",
      "current_depth": "how well this area is currently covered",
      "target_depth": "what level of understanding we should aim for",
      "priority": "high|medium|low",
      "suggested_queries": ["specific search query 1", "specific search query 2"],
      "rationale": "why this area needs deeper investigation"
    }
  ],
  "strategy_summary": "overall research strategy recommendation"
}
"""

# ======================================================================
# Knowledge Service HTTP client
# ======================================================================


class KnowledgeServiceClient:
    """HTTP client for the Knowledge service REST API."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_entities(self, topic: str, top_k: int = 50) -> list[dict[str, Any]]:
        """Retrieve entities for a topic."""
        with tracer.start_as_current_span("knowledge.get_entities") as span:
            span.set_attribute("knowledge.topic", topic)
            span.set_attribute("knowledge.top_k", top_k)
            try:
                resp = await self._client.get(
                    "/entities",
                    params={"topic": topic, "top_k": top_k},
                )
                resp.raise_for_status()
                data = resp.json()
                entities = data.get("entities", data if isinstance(data, list) else [])
                span.set_attribute("knowledge.count", len(entities))
                return entities
            except Exception:
                logger.exception("Failed to fetch entities for topic=%s", topic)
                return []

    async def get_claims(self, topic: str, top_k: int = 50) -> list[dict[str, Any]]:
        """Retrieve claims for a topic."""
        with tracer.start_as_current_span("knowledge.get_claims") as span:
            span.set_attribute("knowledge.topic", topic)
            try:
                resp = await self._client.get(
                    "/claims",
                    params={"topic": topic, "top_k": top_k},
                )
                resp.raise_for_status()
                data = resp.json()
                claims = data.get("claims", data if isinstance(data, list) else [])
                span.set_attribute("knowledge.count", len(claims))
                return claims
            except Exception:
                logger.exception("Failed to fetch claims for topic=%s", topic)
                return []

    async def get_relationships(
        self,
        topic: str,
        entity_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve relationships for a topic or specific entities."""
        with tracer.start_as_current_span("knowledge.get_relationships") as span:
            span.set_attribute("knowledge.topic", topic)
            try:
                params: dict[str, Any] = {"topic": topic}
                if entity_ids:
                    params["entity_ids"] = ",".join(entity_ids)
                resp = await self._client.get("/relationships", params=params)
                resp.raise_for_status()
                data = resp.json()
                rels = data.get("relationships", data if isinstance(data, list) else [])
                span.set_attribute("knowledge.count", len(rels))
                return rels
            except Exception:
                logger.exception("Failed to fetch relationships for topic=%s", topic)
                return []

    async def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Semantic / hybrid search across the knowledge base."""
        with tracer.start_as_current_span("knowledge.search") as span:
            span.set_attribute("knowledge.query", query)
            span.set_attribute("knowledge.top_k", top_k)
            try:
                resp = await self._client.get(
                    "/search",
                    params={"query": query, "top_k": top_k},
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", data if isinstance(data, list) else [])
                span.set_attribute("knowledge.count", len(results))
                return results
            except Exception:
                logger.exception("Knowledge search failed for query=%s", query)
                return []


# ======================================================================
# Reasoning Engine
# ======================================================================


class ReasoningEngine:
    """Executes reasoning strategies over the knowledge graph via RAG."""

    def __init__(
        self,
        config: ReasonerConfig,
        llm: LLMClient,
        knowledge: KnowledgeServiceClient,
    ) -> None:
        self._config = config
        self._llm = llm
        self._knowledge = knowledge

    async def run(self, request: ReasoningRequest) -> ReasoningResult:
        """Dispatch to the appropriate reasoning strategy."""
        with tracer.start_as_current_span("reasoning.run") as span:
            span.set_attribute("reasoning.type", request.reasoning_type)
            span.set_attribute("reasoning.topic", request.topic)
            span.set_attribute("reasoning.request_id", request.request_id)

            start = time.monotonic()

            strategy = {
                "gap_analysis": self._gap_analysis,
                "contradiction_resolution": self._contradiction_resolution,
                "synthesis": self._synthesis,
                "depth_probe": self._depth_probe,
            }.get(request.reasoning_type)

            if strategy is None:
                logger.error("Unknown reasoning type: %s", request.reasoning_type)
                return ReasoningResult(
                    request_id=request.request_id,
                    topic=request.topic,
                )

            result = await strategy(request)
            latency_ms = (time.monotonic() - start) * 1000
            span.set_attribute("reasoning.latency_ms", latency_ms)
            logger.info(
                "Reasoning complete type=%s topic=%s latency=%.0fms",
                request.reasoning_type, request.topic, latency_ms,
            )
            return result

    # ------------------------------------------------------------------
    # Strategy: Gap Analysis
    # ------------------------------------------------------------------

    async def _gap_analysis(self, request: ReasoningRequest) -> ReasoningResult:
        """Identify areas with thin coverage or low confidence."""
        with tracer.start_as_current_span("reasoning.gap_analysis"):
            # RAG: retrieve context from knowledge service
            entities = await self._knowledge.get_entities(request.topic, top_k=100)
            claims = await self._knowledge.get_claims(request.topic, top_k=100)
            relationships = await self._knowledge.get_relationships(request.topic)

            knowledge_count = len(entities) + len(claims) + len(relationships)

            # Build context for the LLM
            context = self._format_knowledge_context(entities, claims, relationships)

            user_prompt = (
                f"Topic: {request.topic}\n\n"
                f"Current knowledge base:\n{context}\n\n"
                f"Additional context from request: {request.context}\n\n"
                f"Analyze the completeness of this knowledge base and identify all gaps."
            )

            data = await self._llm.complete_json(
                GAP_ANALYSIS_SYSTEM_PROMPT,
                user_prompt,
            )

            gaps = [
                KnowledgeGap(
                    topic=request.topic,
                    area=g.get("area", ""),
                    severity=g.get("severity", "moderate"),
                    description=g.get("description", ""),
                    suggested_queries=g.get("suggested_queries", []),
                )
                for g in data.get("gaps", [])
                if g.get("area")
            ]

            return ReasoningResult(
                request_id=request.request_id,
                topic=request.topic,
                gaps=gaps,
                meta=ReasoningMeta(
                    reasoning_type="gap_analysis",
                    model_used=self._config.reasoning_model,
                    knowledge_items_considered=knowledge_count,
                ),
            )

    # ------------------------------------------------------------------
    # Strategy: Contradiction Resolution
    # ------------------------------------------------------------------

    async def _contradiction_resolution(self, request: ReasoningRequest) -> ReasoningResult:
        """Weigh conflicting claims and determine most likely truth."""
        with tracer.start_as_current_span("reasoning.contradiction_resolution"):
            claims = await self._knowledge.get_claims(request.topic, top_k=200)

            if not claims:
                logger.info("No claims found for topic=%s — nothing to resolve", request.topic)
                return ReasoningResult(
                    request_id=request.request_id,
                    topic=request.topic,
                    meta=ReasoningMeta(
                        reasoning_type="contradiction_resolution",
                        model_used=self._config.reasoning_model,
                        knowledge_items_considered=0,
                    ),
                )

            claims_text = "\n".join(
                f"- Claim {c.get('id', 'unknown')} (confidence {c.get('confidence', '?')}): "
                f"\"{c.get('statement', '')}\""
                f" | Evidence: {c.get('supporting_evidence', [])}"
                for c in claims
            )

            user_prompt = (
                f"Topic: {request.topic}\n\n"
                f"Claims to analyze for contradictions:\n{claims_text}\n\n"
                f"Identify any contradictions and resolve them."
            )

            data = await self._llm.complete_json(
                CONTRADICTION_SYSTEM_PROMPT,
                user_prompt,
            )

            resolutions = [
                ContradictionResolution(
                    claim_ids=r.get("claim_ids", []),
                    resolution=r.get("resolution", ""),
                    confidence=float(r.get("confidence", 0.5)),
                    reasoning=r.get("reasoning", ""),
                )
                for r in data.get("resolutions", [])
            ]

            return ReasoningResult(
                request_id=request.request_id,
                topic=request.topic,
                resolutions=resolutions,
                meta=ReasoningMeta(
                    reasoning_type="contradiction_resolution",
                    model_used=self._config.reasoning_model,
                    knowledge_items_considered=len(claims),
                ),
            )

    # ------------------------------------------------------------------
    # Strategy: Synthesis
    # ------------------------------------------------------------------

    async def _synthesis(self, request: ReasoningRequest) -> ReasoningResult:
        """Combine atomic knowledge into higher-order insights."""
        with tracer.start_as_current_span("reasoning.synthesis"):
            entities = await self._knowledge.get_entities(request.topic, top_k=100)
            claims = await self._knowledge.get_claims(request.topic, top_k=100)
            relationships = await self._knowledge.get_relationships(request.topic)

            # Also do a semantic search for additional context
            search_results = await self._knowledge.search(request.topic, top_k=20)

            knowledge_count = len(entities) + len(claims) + len(relationships) + len(search_results)
            context = self._format_knowledge_context(entities, claims, relationships)

            search_context = ""
            if search_results:
                search_items = [
                    r.get("content", r.get("description", str(r)))
                    for r in search_results[:10]
                ]
                search_context = f"\n\nAdditional search results:\n" + "\n".join(
                    f"- {item}" for item in search_items
                )

            user_prompt = (
                f"Topic: {request.topic}\n\n"
                f"Knowledge base:\n{context}"
                f"{search_context}\n\n"
                f"Synthesize higher-order insights from this knowledge."
            )

            data = await self._llm.complete_json(
                SYNTHESIS_SYSTEM_PROMPT,
                user_prompt,
            )

            insights = [
                Insight(
                    topic=request.topic,
                    statement=i.get("statement", ""),
                    supporting_entities=i.get("supporting_entities", []),
                    confidence=float(i.get("confidence", 0.5)),
                    reasoning_chain=i.get("reasoning_chain", ""),
                )
                for i in data.get("insights", [])
                if i.get("statement")
            ]

            return ReasoningResult(
                request_id=request.request_id,
                topic=request.topic,
                insights=insights,
                meta=ReasoningMeta(
                    reasoning_type="synthesis",
                    model_used=self._config.reasoning_model,
                    knowledge_items_considered=knowledge_count,
                ),
            )

    # ------------------------------------------------------------------
    # Strategy: Depth Probe
    # ------------------------------------------------------------------

    async def _depth_probe(self, request: ReasoningRequest) -> ReasoningResult:
        """Identify areas warranting deeper investigation."""
        with tracer.start_as_current_span("reasoning.depth_probe"):
            entities = await self._knowledge.get_entities(request.topic, top_k=100)
            claims = await self._knowledge.get_claims(request.topic, top_k=50)

            knowledge_count = len(entities) + len(claims)
            context = self._format_knowledge_context(entities, claims, [])

            user_prompt = (
                f"Topic: {request.topic}\n\n"
                f"Current knowledge:\n{context}\n\n"
                f"Identify areas that need deeper investigation and suggest research strategies."
            )

            data = await self._llm.complete_json(
                DEPTH_PROBE_SYSTEM_PROMPT,
                user_prompt,
            )

            # Depth probes produce both gaps (areas to explore) and insights
            # (strategic recommendations)
            gaps: list[KnowledgeGap] = []
            for probe in data.get("probes", []):
                priority_to_severity = {"high": "critical", "medium": "moderate", "low": "minor"}
                gaps.append(
                    KnowledgeGap(
                        topic=request.topic,
                        area=probe.get("area", ""),
                        severity=priority_to_severity.get(probe.get("priority", "medium"), "moderate"),
                        description=(
                            f"Current: {probe.get('current_depth', 'unknown')}. "
                            f"Target: {probe.get('target_depth', 'unknown')}. "
                            f"{probe.get('rationale', '')}"
                        ),
                        suggested_queries=probe.get("suggested_queries", []),
                    )
                )

            strategy = data.get("strategy_summary", "")
            insights = []
            if strategy:
                insights.append(
                    Insight(
                        topic=request.topic,
                        statement=strategy,
                        confidence=0.7,
                        reasoning_chain="depth_probe_strategy",
                    )
                )

            return ReasoningResult(
                request_id=request.request_id,
                topic=request.topic,
                insights=insights,
                gaps=gaps,
                meta=ReasoningMeta(
                    reasoning_type="depth_probe",
                    model_used=self._config.reasoning_model,
                    knowledge_items_considered=knowledge_count,
                ),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_knowledge_context(
        entities: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> str:
        """Build a structured text context from knowledge items."""
        parts: list[str] = []

        if entities:
            entity_lines = []
            for e in entities[:80]:
                name = e.get("name", "?")
                etype = e.get("entity_type", "?")
                desc = e.get("description", "")
                conf = e.get("confidence", "?")
                entity_lines.append(f"  - [{etype}] {name}: {desc} (confidence: {conf})")
            parts.append("ENTITIES:\n" + "\n".join(entity_lines))

        if claims:
            claim_lines = []
            for c in claims[:60]:
                stmt = c.get("statement", "?")
                conf = c.get("confidence", "?")
                claim_lines.append(f"  - \"{stmt}\" (confidence: {conf})")
            parts.append("CLAIMS:\n" + "\n".join(claim_lines))

        if relationships:
            rel_lines = []
            for r in relationships[:40]:
                src = r.get("source_entity_id", r.get("source_entity", "?"))
                tgt = r.get("target_entity_id", r.get("target_entity", "?"))
                rtype = r.get("relationship_type", r.get("type", "?"))
                rel_lines.append(f"  - {src} --[{rtype}]--> {tgt}")
            parts.append("RELATIONSHIPS:\n" + "\n".join(rel_lines))

        return "\n\n".join(parts) if parts else "(empty knowledge base)"
