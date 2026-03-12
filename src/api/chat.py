"""Chat endpoint implementation — RAG-powered expert Q&A.

Flow:
1. Accept user question (optionally scoped to a topic)
2. Search the knowledge graph for relevant entities, claims
3. Build a RAG context window from the search results
4. Call Azure AI Foundry LLM for a grounded response
5. Return the answer with citations and confidence
"""

from __future__ import annotations

import logging
from typing import Any

from azure.ai.inference.aio import ChatCompletionsClient
from azure.ai.inference.models import (
    SystemMessage,
    UserMessage,
)
from azure.identity.aio import DefaultAzureCredential
from opentelemetry import trace

from .config import AIFoundryConfig
from .knowledge_client import KnowledgeClient
from .models import ChatRequest, ChatResponse, Citation

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_SYSTEM_PROMPT = """\
You are an expert AI assistant backed by a curated knowledge graph.
Answer the user's question using ONLY the context provided below.
If the context does not contain enough information, say so honestly.
Always cite your sources by referencing entity names or source URLs from the context.
Be precise, thorough, and scholarly. Provide confidence in your answer.
"""


class ChatHandler:
    """Handles chat requests using RAG over the knowledge graph."""

    def __init__(
        self,
        ai_config: AIFoundryConfig,
        knowledge: KnowledgeClient,
    ) -> None:
        self._ai_config = ai_config
        self._knowledge = knowledge
        self._credential: DefaultAzureCredential | None = None
        self._llm_client: ChatCompletionsClient | None = None

    async def initialize(self) -> None:
        self._credential = DefaultAzureCredential()
        self._llm_client = ChatCompletionsClient(
            endpoint=self._ai_config.endpoint,
            credential=self._credential,
        )
        logger.info("Chat handler initialized with model %s", self._ai_config.chat_model)

    async def close(self) -> None:
        if self._llm_client:
            await self._llm_client.close()
        if self._credential:
            await self._credential.close()

    @tracer.start_as_current_span("chat.handle")
    async def handle(self, request: ChatRequest) -> ChatResponse:
        """Process a chat request end-to-end."""
        # 1. Search for relevant knowledge
        context_parts, citations = await self._gather_context(request)

        # 2. Build prompt
        context_text = "\n\n".join(context_parts) if context_parts else "No relevant context found in the knowledge graph."
        user_prompt = self._build_user_prompt(request, context_text)

        # 3. Call LLM
        answer, tokens_used = await self._call_llm(user_prompt)

        # 4. Compute rough confidence from citation relevance
        confidence = self._estimate_confidence(citations, answer)

        return ChatResponse(
            answer=answer,
            confidence=confidence,
            sources=citations,
            topic=request.topic,
            model=self._ai_config.chat_model,
            tokens_used=tokens_used,
        )

    # ── Context gathering ──────────────────────────────────────────────

    async def _gather_context(
        self, request: ChatRequest
    ) -> tuple[list[str], list[Citation]]:
        """Search the knowledge graph and build RAG context."""
        context_parts: list[str] = []
        citations: list[Citation] = []

        # Hybrid search for relevant documents
        try:
            search_results = await self._knowledge.search(
                q=request.question,
                topic=request.topic,
                limit=15,
                mode="hybrid",
            )
            for item in search_results.get("items", []):
                doc_type = item.get("doc_type", "")
                if doc_type == "Entity":
                    text = f"[Entity] {item.get('name', '')}: {item.get('description', item.get('statement', ''))}"
                elif doc_type == "Claim":
                    text = f"[Claim] {item.get('statement', '')}"
                else:
                    text = f"[{doc_type}] {item.get('name', item.get('statement', ''))}"
                context_parts.append(text)
                citations.append(
                    Citation(
                        entity_id=item.get("id", ""),
                        name=item.get("name", item.get("statement", "")[:80]),
                        confidence=item.get("confidence", 0.0),
                        snippet=text[:200],
                    )
                )
        except Exception:
            logger.warning("Hybrid search failed during chat; falling back to entity search", exc_info=True)

        # Supplement with direct entity search if topic provided
        if request.topic:
            try:
                entities = await self._knowledge.search_entities(
                    topic=request.topic, q=request.question, limit=10
                )
                for ent in entities:
                    name = ent.get("name", "")
                    desc = ent.get("description", "")
                    if desc and f"[Entity] {name}" not in " ".join(context_parts):
                        context_parts.append(f"[Entity] {name}: {desc}")
                        source_urls = ent.get("source_urls", [])
                        citations.append(
                            Citation(
                                entity_id=ent.get("id", ""),
                                name=name,
                                source_url=source_urls[0] if source_urls else "",
                                confidence=ent.get("confidence", 0.0),
                                snippet=desc[:200],
                            )
                        )
            except Exception:
                logger.warning("Entity search fallback also failed", exc_info=True)

        # Add claims for extra depth
        if request.topic:
            try:
                claims = await self._knowledge.query_claims(
                    topic=request.topic, min_confidence=0.5, limit=10
                )
                for claim in claims:
                    stmt = claim.get("statement", "")
                    if stmt and stmt not in " ".join(context_parts):
                        context_parts.append(f"[Claim] {stmt}")
            except Exception:
                logger.warning("Claim search failed", exc_info=True)

        # Include user-supplied context
        if request.context:
            context_parts.append(f"[User Context] {request.context}")

        return context_parts, citations

    # ── Prompt building ────────────────────────────────────────────────

    @staticmethod
    def _build_user_prompt(request: ChatRequest, context: str) -> str:
        prompt = f"## Context from Knowledge Graph\n\n{context}\n\n"
        prompt += f"## Question\n\n{request.question}\n\n"
        prompt += "Provide a thorough, well-cited answer. If information is insufficient, state what is missing."
        if request.topic:
            prompt += f"\n\nNote: This question is about the topic '{request.topic}'."
        return prompt

    # ── LLM call ───────────────────────────────────────────────────────

    async def _call_llm(self, user_prompt: str) -> tuple[str, int]:
        """Call Azure AI Foundry chat completion endpoint."""
        assert self._llm_client is not None
        with tracer.start_as_current_span("chat.llm_call") as span:
            span.set_attribute("llm.model", self._ai_config.chat_model)
            try:
                response = await self._llm_client.complete(
                    model=self._ai_config.chat_model,
                    messages=[
                        SystemMessage(content=_SYSTEM_PROMPT),
                        UserMessage(content=user_prompt),
                    ],
                    max_tokens=self._ai_config.max_tokens,
                    temperature=self._ai_config.temperature,
                )
                answer = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                span.set_attribute("llm.tokens", tokens)
                return answer, tokens
            except Exception as exc:
                logger.exception("LLM call failed")
                span.record_exception(exc)
                return (
                    "I'm unable to generate a response at this time. "
                    "The AI model is currently unavailable. Please try again later.",
                    0,
                )

    # ── Confidence estimation ──────────────────────────────────────────

    @staticmethod
    def _estimate_confidence(citations: list[Citation], answer: str) -> float:
        """Rough confidence score based on citation quality and coverage."""
        if not citations:
            return 0.1
        avg_citation_conf = sum(c.confidence for c in citations) / len(citations)
        # Boost if we have many sources
        source_boost = min(len(citations) / 10.0, 0.3)
        # Penalize if model admitted uncertainty
        uncertainty_penalty = 0.0
        uncertainty_phrases = ["i don't know", "insufficient", "not enough information", "no relevant context"]
        answer_lower = answer.lower()
        for phrase in uncertainty_phrases:
            if phrase in answer_lower:
                uncertainty_penalty = 0.3
                break
        confidence = min(avg_citation_conf + source_boost - uncertainty_penalty, 1.0)
        return round(max(confidence, 0.05), 4)
