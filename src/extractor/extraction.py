"""Core extraction pipeline — chunk, extract, embed.

Orchestrates the full knowledge-extraction flow:

1. **Chunk** — split long documents with overlap for context continuity.
2. **Extract entities** — LLM call per chunk → deduplicate across chunks.
3. **Extract relationships** — LLM call with entity list + text.
4. **Extract claims** — LLM call per chunk with evidence tracking.
5. **Summarize** — multi-level summaries over the full document.
6. **Embed** — vector embeddings for every entity.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from opentelemetry import trace

from config import ExtractorConfig
from llm_client import LLMClient
from models import Claim, Entity, ExtractionResult, Relationship, Summary

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("extractor.pipeline")

# ======================================================================
# Prompt templates — real, detailed, with few-shot examples
# ======================================================================

ENTITY_SYSTEM_PROMPT = """\
You are an expert knowledge-extraction system.  Your task is to identify and
extract **all** meaningful entities from the provided text about a specific topic.

## Entity types
- person: Named individuals (researchers, authors, executives)
- organization: Companies, institutions, research labs, government bodies
- concept: Abstract ideas, theories, paradigms, principles
- technology: Software, hardware, algorithms, models, systems
- method: Techniques, approaches, processes, methodologies
- metric: Measurements, benchmarks, scores, statistics
- location: Geographic places, regions
- event: Conferences, releases, incidents, milestones
- other: Entities that don't fit the above categories

## Rules
1. Extract ALL meaningful entities — be thorough, not selective.
2. Normalize names to canonical form ("LLMs" → "Large Language Model").
3. Provide a concise, factual description based ONLY on what the text states.
4. Confidence scores:
   • 0.90–1.00 — explicitly named and clearly defined
   • 0.70–0.89 — mentioned but not fully described
   • 0.50–0.69 — implied or indirectly referenced
   • Below 0.50 — do not include
5. If the text is empty, unintelligible, or entirely non-English, return
   {"entities": []}.
6. Return ONLY valid JSON.

## Output format
{
  "entities": [
    {
      "name": "canonical entity name",
      "entity_type": "person|organization|concept|technology|method|metric|location|event|other",
      "description": "brief factual description from the text",
      "confidence": 0.95
    }
  ]
}

## Example

Input text: "Researchers at DeepMind published AlphaFold 2 in Nature, achieving
atomic-level accuracy in protein structure prediction using attention mechanisms."

Output:
{
  "entities": [
    {"name": "DeepMind", "entity_type": "organization", "description": "AI research laboratory that published AlphaFold 2", "confidence": 0.98},
    {"name": "AlphaFold 2", "entity_type": "technology", "description": "AI system for protein structure prediction with atomic-level accuracy", "confidence": 0.99},
    {"name": "Nature", "entity_type": "organization", "description": "Scientific journal where the AlphaFold 2 research was published", "confidence": 0.95},
    {"name": "Protein Structure Prediction", "entity_type": "concept", "description": "Determining 3D structures of proteins from amino-acid sequences", "confidence": 0.93},
    {"name": "Attention Mechanism", "entity_type": "concept", "description": "Neural-network technique used in AlphaFold 2", "confidence": 0.90}
  ]
}
"""

RELATIONSHIP_SYSTEM_PROMPT = """\
You are an expert knowledge-extraction system specializing in identifying
relationships between entities.

Given a text and a list of previously extracted entity names, find all
meaningful directed relationships between them.

## Relationship types
- developed_by: X was created/built by Y
- part_of: X is a component/subset of Y
- uses: X utilizes/employs Y
- related_to: topical association (use sparingly — prefer specific types)
- compared_to: X is evaluated against Y
- derived_from: X is based on / evolved from Y
- enables: X makes Y possible or improves Y
- contradicts: X conflicts with Y
- supports: X provides evidence for Y
- authored_by: X was written by person Y
- located_in: X is geographically in Y
- instance_of: X is a specific example of Y
- predecessor_of: X came before Y
- successor_of: X came after and evolved from Y
- measured_by: X is evaluated using metric Y

## Rules
1. Only create relationships between entities in the provided list.
2. Use entity names exactly as given.
3. Prefer specific types over "related_to".
4. Confidence 0.5–1.0.  If no relationships are found return {"relationships": []}.
5. Return ONLY valid JSON.

## Output format
{
  "relationships": [
    {
      "source_entity": "entity name",
      "target_entity": "entity name",
      "relationship_type": "type",
      "description": "brief description",
      "confidence": 0.9
    }
  ]
}

## Example
Entities: ["AlphaFold 2", "DeepMind", "Attention Mechanism", "Protein Structure Prediction"]
Text: "DeepMind's AlphaFold 2 uses attention mechanisms to predict protein structures."

Output:
{
  "relationships": [
    {"source_entity": "AlphaFold 2", "target_entity": "DeepMind", "relationship_type": "developed_by", "description": "AlphaFold 2 was developed by DeepMind", "confidence": 0.98},
    {"source_entity": "AlphaFold 2", "target_entity": "Attention Mechanism", "relationship_type": "uses", "description": "AlphaFold 2 uses attention mechanisms in its architecture", "confidence": 0.95},
    {"source_entity": "AlphaFold 2", "target_entity": "Protein Structure Prediction", "relationship_type": "enables", "description": "AlphaFold 2 enables accurate protein structure prediction", "confidence": 0.96}
  ]
}
"""

CLAIM_SYSTEM_PROMPT = """\
You are an expert knowledge-extraction system specializing in identifying
factual claims and assertions.  Extract all verifiable statements.

## What counts as a claim
- A statement asserting something is true/false or has a specific value.
- Quantitative assertions (numbers, percentages, comparisons).
- Causal claims (X causes / leads to Y).
- Evaluative claims (X is better / worse than Y).
- Definitional claims (X is defined as Y).

## Rules
1. Each claim must be self-contained — understandable without the source text.
2. Include supporting evidence (quotes / data points from the text).
3. Note contradicting evidence from the same text if any.
4. Confidence:
   • 0.90–1.00 — directly stated with cited evidence
   • 0.70–0.89 — clearly stated as fact
   • 0.50–0.69 — hedged ("may", "possibly", "suggests")
   • Below 0.50 — do not include
5. If no claims can be extracted, return {"claims": []}.
6. Return ONLY valid JSON.

## Output format
{
  "claims": [
    {
      "statement": "self-contained factual claim",
      "confidence": 0.85,
      "supporting_evidence": ["direct quote or data point"],
      "contradicting_evidence": ["counter-evidence if any"]
    }
  ]
}

## Example
Text: "GPT-4 achieves 86.4% on MMLU, a 15-point improvement over GPT-3.5.
However, critics note potential benchmark contamination."

Output:
{
  "claims": [
    {"statement": "GPT-4 achieves 86.4% accuracy on the MMLU benchmark", "confidence": 0.95, "supporting_evidence": ["achieves 86.4% on MMLU"], "contradicting_evidence": ["critics note potential benchmark contamination"]},
    {"statement": "GPT-4 outperforms GPT-3.5 by 15 percentage points on MMLU", "confidence": 0.93, "supporting_evidence": ["a 15-point improvement over GPT-3.5"], "contradicting_evidence": []},
    {"statement": "The MMLU benchmark may be affected by training-data contamination", "confidence": 0.60, "supporting_evidence": ["critics note potential benchmark contamination"], "contradicting_evidence": []}
  ]
}
"""

SUMMARY_SYSTEM_PROMPT = """\
You are an expert knowledge-summarization system.  Generate summaries at three
levels of detail for the given text about a specific topic.

## Levels
1. **overview** — 2-3 sentences capturing the main point and significance.
2. **subtopic** — one paragraph covering key themes, arguments, and sub-topics.
3. **finding** — a detailed paragraph listing specific findings, data points,
   and conclusions.

## Rules
1. Be strictly factual — never add information not in the text.
2. Reference specific entity names where relevant.
3. Preserve numerical data and metrics exactly.
4. List referenced entity names under entity_refs.
5. For very short or empty text, produce proportionally shorter summaries.

## Output format
{
  "summaries": [
    {
      "level": "overview",
      "content": "2-3 sentence summary",
      "entity_refs": ["Entity1", "Entity2"]
    },
    {
      "level": "subtopic",
      "content": "key-themes paragraph",
      "entity_refs": ["Entity1"]
    },
    {
      "level": "finding",
      "content": "detailed findings paragraph",
      "entity_refs": ["Entity1", "Entity3"]
    }
  ]
}
"""

# ======================================================================
# Document chunking
# ======================================================================


def chunk_document(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split *text* into overlapping chunks, preferring natural boundaries.

    Tries paragraph breaks (``\\n\\n``), then sentence endings (``. ``),
    before falling back to a hard character split.
    """
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            # Try to snap to a paragraph boundary in the second half
            mid = start + chunk_size // 2
            para = text.rfind("\n\n", mid, end)
            if para != -1:
                end = para + 2
            else:
                # Try sentence boundaries
                for sep in (". ", ".\n", "! ", "? "):
                    sent = text.rfind(sep, mid, end)
                    if sent != -1:
                        end = sent + len(sep)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        next_start = max(start + 1, end - overlap)
        if next_start <= start:
            next_start = start + 1
        start = next_start

    return chunks


# ======================================================================
# Extraction pipeline
# ======================================================================


class ExtractionPipeline:
    """Orchestrates the full extraction flow for a single document."""

    def __init__(self, config: ExtractorConfig, llm: LLMClient) -> None:
        self._config = config
        self._llm = llm

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------

    async def run(
        self,
        text: str,
        topic: str,
        source_url: str,
        request_id: str,
    ) -> ExtractionResult:
        """Execute the full pipeline: chunk → extract → embed → result."""
        with tracer.start_as_current_span("extraction.pipeline") as span:
            span.set_attribute("extraction.topic", topic)
            span.set_attribute("extraction.request_id", request_id)
            span.set_attribute("extraction.text_length", len(text))

            chunks = chunk_document(
                text,
                self._config.chunk_size,
                self._config.chunk_overlap,
            )
            span.set_attribute("extraction.chunk_count", len(chunks))

            if not chunks:
                logger.warning("No chunks produced for request %s — empty content", request_id)
                return ExtractionResult(request_id=request_id, topic=topic)

            # --- Entity extraction (parallel across chunks) ---
            entity_lists = await asyncio.gather(
                *(self._extract_entities(chunk, topic) for chunk in chunks)
            )
            raw_entities = [e for batch in entity_lists for e in batch]
            entities = _deduplicate_entities(raw_entities)
            for ent in entities:
                ent.topic = topic
                ent.source_url = source_url

            span.set_attribute("extraction.raw_entity_count", len(raw_entities))
            span.set_attribute("extraction.entity_count", len(entities))

            # --- Relationship extraction (parallel across chunks) ---
            entity_names = [e.name for e in entities]
            rel_lists = await asyncio.gather(
                *(self._extract_relationships(chunk, entity_names, topic) for chunk in chunks)
            )
            raw_relationships = [r for batch in rel_lists for r in batch]
            entity_name_to_id = {e.name.lower(): e.id for e in entities}
            relationships = _resolve_relationships(raw_relationships, entity_name_to_id)

            span.set_attribute("extraction.relationship_count", len(relationships))

            # --- Claim extraction (parallel across chunks) ---
            claim_lists = await asyncio.gather(
                *(self._extract_claims(chunk, topic, source_url) for chunk in chunks)
            )
            claims = [c for batch in claim_lists for c in batch]
            span.set_attribute("extraction.claim_count", len(claims))

            # --- Summaries (over full text) ---
            full_text = text[:16000]  # cap for token budget
            summaries = await self._generate_summaries(full_text, topic, source_url)
            span.set_attribute("extraction.summary_count", len(summaries))

            # --- Embeddings ---
            entities = await self._embed_entities(entities)

            logger.info(
                "Extraction complete request=%s entities=%d rels=%d claims=%d summaries=%d",
                request_id, len(entities), len(relationships), len(claims), len(summaries),
            )

            return ExtractionResult(
                request_id=request_id,
                topic=topic,
                entities=entities,
                relationships=relationships,
                claims=claims,
                summaries=summaries,
            )

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    async def _extract_entities(self, chunk: str, topic: str) -> list[Entity]:
        """Extract entities from a single chunk via LLM."""
        with tracer.start_as_current_span("extraction.entities"):
            user_prompt = (
                f"Topic: {topic}\n\n"
                f"Text to extract entities from:\n\"\"\"\n{chunk}\n\"\"\""
            )
            try:
                data = await self._llm.complete_json(
                    ENTITY_SYSTEM_PROMPT, user_prompt,
                )
                raw_entities = data.get("entities", [])
                return [
                    Entity(
                        name=e["name"],
                        entity_type=e.get("entity_type", "other"),
                        description=e.get("description", ""),
                        confidence=float(e.get("confidence", 0.5)),
                    )
                    for e in raw_entities
                    if e.get("name")
                ]
            except Exception:
                logger.exception("Entity extraction failed for chunk (len=%d)", len(chunk))
                return []

    # ------------------------------------------------------------------
    # Relationship extraction
    # ------------------------------------------------------------------

    async def _extract_relationships(
        self,
        chunk: str,
        entity_names: list[str],
        topic: str,
    ) -> list[dict[str, Any]]:
        """Extract relationships between known entities from a chunk."""
        if not entity_names:
            return []

        with tracer.start_as_current_span("extraction.relationships"):
            names_str = ", ".join(f'"{n}"' for n in entity_names)
            user_prompt = (
                f"Topic: {topic}\n\n"
                f"Known entities: [{names_str}]\n\n"
                f"Text:\n\"\"\"\n{chunk}\n\"\"\""
            )
            try:
                data = await self._llm.complete_json(
                    RELATIONSHIP_SYSTEM_PROMPT, user_prompt,
                )
                return data.get("relationships", [])
            except Exception:
                logger.exception("Relationship extraction failed for chunk (len=%d)", len(chunk))
                return []

    # ------------------------------------------------------------------
    # Claim extraction
    # ------------------------------------------------------------------

    async def _extract_claims(
        self, chunk: str, topic: str, source_url: str,
    ) -> list[Claim]:
        """Extract claims from a single chunk."""
        with tracer.start_as_current_span("extraction.claims"):
            user_prompt = (
                f"Topic: {topic}\n\n"
                f"Text to extract claims from:\n\"\"\"\n{chunk}\n\"\"\""
            )
            try:
                data = await self._llm.complete_json(
                    CLAIM_SYSTEM_PROMPT, user_prompt,
                )
                return [
                    Claim(
                        statement=c["statement"],
                        topic=topic,
                        confidence=float(c.get("confidence", 0.5)),
                        source_url=source_url,
                        supporting_evidence=c.get("supporting_evidence", []),
                        contradicting_evidence=c.get("contradicting_evidence", []),
                    )
                    for c in data.get("claims", [])
                    if c.get("statement")
                ]
            except Exception:
                logger.exception("Claim extraction failed for chunk (len=%d)", len(chunk))
                return []

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    async def _generate_summaries(
        self, text: str, topic: str, source_url: str,
    ) -> list[Summary]:
        """Generate multi-level summaries for the full document."""
        with tracer.start_as_current_span("extraction.summaries"):
            user_prompt = f"Topic: {topic}\n\nText to summarize:\n\"\"\"\n{text}\n\"\"\""
            try:
                data = await self._llm.complete_json(
                    SUMMARY_SYSTEM_PROMPT, user_prompt,
                )
                return [
                    Summary(
                        topic=topic,
                        level=s.get("level", "overview"),
                        content=s.get("content", ""),
                        entity_refs=s.get("entity_refs", []),
                        source_urls=[source_url],
                    )
                    for s in data.get("summaries", [])
                    if s.get("content")
                ]
            except Exception:
                logger.exception("Summary generation failed")
                return []

    # ------------------------------------------------------------------
    # Embedding generation
    # ------------------------------------------------------------------

    async def _embed_entities(self, entities: list[Entity]) -> list[Entity]:
        """Generate embeddings for each entity's description."""
        if not entities:
            return entities

        with tracer.start_as_current_span("extraction.embed") as span:
            texts = [
                f"{e.name}: {e.description}" if e.description else e.name
                for e in entities
            ]
            span.set_attribute("extraction.embed_count", len(texts))

            try:
                vectors = await self._llm.embed(texts)
                for entity, vec in zip(entities, vectors):
                    entity.embedding = vec
                logger.info("Embedded %d entities", len(entities))
            except Exception:
                logger.exception("Embedding generation failed — entities returned without vectors")

        return entities


# ======================================================================
# Helpers
# ======================================================================


def _deduplicate_entities(entities: list[Entity]) -> list[Entity]:
    """Merge entities with the same canonical name, keeping highest confidence."""
    by_name: dict[str, Entity] = {}
    for entity in entities:
        key = entity.name.lower().strip()
        if key in by_name:
            existing = by_name[key]
            if entity.confidence > existing.confidence:
                # Prefer the higher-confidence version, keep merged description
                if not entity.description and existing.description:
                    entity.description = existing.description
                by_name[key] = entity
        else:
            by_name[key] = entity
    return list(by_name.values())


def _resolve_relationships(
    raw_rels: list[dict[str, Any]],
    name_to_id: dict[str, str],
) -> list[Relationship]:
    """Convert raw LLM relationship dicts into Relationship models.

    Only relationships where both entity names can be resolved to known IDs
    are kept.
    """
    resolved: list[Relationship] = []
    for r in raw_rels:
        src_name = (r.get("source_entity") or "").lower().strip()
        tgt_name = (r.get("target_entity") or "").lower().strip()
        src_id = name_to_id.get(src_name)
        tgt_id = name_to_id.get(tgt_name)
        if src_id and tgt_id:
            resolved.append(
                Relationship(
                    id=str(uuid.uuid4()),
                    source_entity_id=src_id,
                    target_entity_id=tgt_id,
                    relationship_type=r.get("relationship_type", "related_to"),
                    description=r.get("description", ""),
                    confidence=float(r.get("confidence", 0.5)),
                )
            )
        else:
            logger.debug(
                "Dropped unresolvable relationship %s → %s",
                r.get("source_entity"), r.get("target_entity"),
            )
    return resolved
