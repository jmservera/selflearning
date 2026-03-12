"""Azure AI Foundry LLM client with tracing, retry, and structured output.

Provides a model-agnostic interface over the azure-ai-inference SDK.
Every call is instrumented with OpenTelemetry spans that record model name,
token counts, and latency — making LLM usage fully traceable.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from azure.ai.inference.aio import ChatCompletionsClient, EmbeddingsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.identity.aio import DefaultAzureCredential
from opentelemetry import trace

from config import ExtractorConfig

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("extractor.llm")


class LLMClient:
    """Async wrapper around Azure AI Foundry chat and embedding APIs.

    Usage::

        client = LLMClient(config)
        await client.initialize()
        result = await client.complete_json(system, user)
        vectors = await client.embed(["hello world"])
        await client.close()
    """

    def __init__(self, config: ExtractorConfig) -> None:
        self._config = config
        self._credential: DefaultAzureCredential | None = None
        self._chat_client: ChatCompletionsClient | None = None
        self._embed_client: EmbeddingsClient | None = None

    async def initialize(self) -> None:
        """Create underlying SDK clients with managed-identity auth."""
        self._credential = DefaultAzureCredential()
        self._chat_client = ChatCompletionsClient(
            endpoint=self._config.azure_ai_endpoint,
            credential=self._credential,
        )
        self._embed_client = EmbeddingsClient(
            endpoint=self._config.azure_ai_endpoint,
            credential=self._credential,
        )
        logger.info(
            "LLM clients initialized (endpoint=%s, model=%s, embed=%s)",
            self._config.azure_ai_endpoint,
            self._config.extraction_model,
            self._config.embedding_model,
        )

    async def close(self) -> None:
        """Release SDK clients and credential."""
        for resource in (self._chat_client, self._embed_client, self._credential):
            if resource is not None:
                await resource.close()
        logger.info("LLM clients closed")

    # ------------------------------------------------------------------
    # Chat completions
    # ------------------------------------------------------------------

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Chat completion expecting a JSON response.

        Automatically retries on JSON-parse failures up to ``max_retries``.
        """
        model = model or self._config.extraction_model
        temperature = temperature if temperature is not None else self._config.extraction_temperature
        max_tokens = max_tokens or self._config.max_tokens

        last_error: Exception | None = None
        for attempt in range(1, self._config.max_retries + 1):
            with tracer.start_as_current_span("llm.complete_json") as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.attempt", attempt)
                span.set_attribute("llm.temperature", temperature)

                start = time.monotonic()
                try:
                    assert self._chat_client is not None, "LLMClient not initialized"
                    response = await self._chat_client.complete(
                        messages=[
                            SystemMessage(content=system_prompt),
                            UserMessage(content=user_prompt),
                        ],
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                    )
                    latency_ms = (time.monotonic() - start) * 1000
                    self._record_usage(span, response, latency_ms)

                    raw = response.choices[0].message.content
                    return self._parse_json(raw)

                except json.JSONDecodeError as exc:
                    last_error = exc
                    logger.warning(
                        "JSON parse error on attempt %d/%d: %s",
                        attempt, self._config.max_retries, exc,
                    )
                    span.set_attribute("llm.error", "json_parse_failed")
                except Exception as exc:
                    last_error = exc
                    latency_ms = (time.monotonic() - start) * 1000
                    span.set_attribute("llm.latency_ms", latency_ms)
                    span.set_attribute("llm.error", str(type(exc).__name__))
                    logger.warning(
                        "LLM call error on attempt %d/%d: %s",
                        attempt, self._config.max_retries, exc,
                    )

        raise RuntimeError(
            f"LLM JSON call failed after {self._config.max_retries} attempts: {last_error}"
        )

    async def complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Chat completion returning plain text."""
        model = model or self._config.extraction_model
        temperature = temperature if temperature is not None else self._config.extraction_temperature
        max_tokens = max_tokens or self._config.max_tokens

        with tracer.start_as_current_span("llm.complete_text") as span:
            span.set_attribute("llm.model", model)

            start = time.monotonic()
            assert self._chat_client is not None, "LLMClient not initialized"
            response = await self._chat_client.complete(
                messages=[
                    SystemMessage(content=system_prompt),
                    UserMessage(content=user_prompt),
                ],
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency_ms = (time.monotonic() - start) * 1000
            self._record_usage(span, response, latency_ms)
            return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Automatically batches inputs according to ``embedding_batch_size``.
        """
        model = model or self._config.embedding_model
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        batch_size = self._config.embedding_batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            with tracer.start_as_current_span("llm.embed") as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.input_count", len(batch))
                span.set_attribute("llm.batch_index", i // batch_size)

                start = time.monotonic()
                assert self._embed_client is not None, "LLMClient not initialized"
                response = await self._embed_client.embed(
                    input=batch,
                    model=model,
                )
                latency_ms = (time.monotonic() - start) * 1000

                span.set_attribute("llm.latency_ms", latency_ms)
                if response.usage:
                    span.set_attribute("llm.total_tokens", response.usage.total_tokens)

                logger.debug(
                    "Embedding batch %d: %d texts in %.0fms",
                    i // batch_size, len(batch), latency_ms,
                )
                all_embeddings.extend(item.embedding for item in response.data)

        return all_embeddings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _record_usage(span: trace.Span, response: Any, latency_ms: float) -> None:
        """Record standard LLM metrics on an OTel span."""
        span.set_attribute("llm.latency_ms", latency_ms)
        if response.usage:
            span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
            span.set_attribute("llm.completion_tokens", response.usage.completion_tokens)
            span.set_attribute("llm.total_tokens", response.usage.total_tokens)
        if response.model:
            span.set_attribute("llm.response_model", response.model)
        logger.debug(
            "LLM call: model=%s tokens=%s latency=%.0fms",
            response.model,
            response.usage.total_tokens if response.usage else "?",
            latency_ms,
        )

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Parse JSON from LLM output, handling markdown code fences."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Drop opening fence (```json or ```) and closing fence (```)
            inner = []
            for line in lines[1:]:
                if line.strip() == "```":
                    break
                inner.append(line)
            text = "\n".join(inner)
        return json.loads(text)
