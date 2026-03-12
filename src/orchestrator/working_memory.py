"""Working memory for the autonomous learning agent.

Provides a short-term context window that the LLM uses during planning
and strategy decisions. Items decay over time as the agent shifts focus,
ensuring the context window stays relevant to current activities.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from opentelemetry import trace

from config import OrchestratorSettings
from models import MemoryItem

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class WorkingMemory:
    """In-process working memory for the learning agent.

    The working memory stores recent findings, gaps, insights, plans, and
    errors.  Each item has a *relevance* score that decays every tick for
    items not associated with the currently focused topic.  When the memory
    exceeds its capacity, the lowest-relevance items are evicted.

    The memory is designed to be serialised into an LLM prompt so the model
    has up-to-date context for planning and strategy decisions.
    """

    def __init__(self, settings: OrchestratorSettings) -> None:
        self._max_items = settings.working_memory_max_items
        self._decay_factor = settings.working_memory_decay_factor
        self._items: list[MemoryItem] = []
        self._current_topic: str | None = None
        self._topic_summaries: dict[str, str] = {}
        # Track how many times each topic has been focused — used for context
        self._focus_counts: dict[str, int] = defaultdict(int)

    # ── Core operations ───────────────────────────────────────────────

    def add(
        self,
        topic: str,
        content: str,
        item_type: str = "finding",
        relevance: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        """Add an item to working memory."""
        with tracer.start_as_current_span("working_memory.add"):
            item = MemoryItem(
                topic=topic,
                content=content,
                item_type=item_type,
                relevance=min(relevance, 1.0),
                metadata=metadata or {},
            )
            self._items.append(item)
            self._enforce_capacity()
            logger.debug(
                "WM add [%s] %s: %.60s (relevance=%.2f, total=%d)",
                item_type,
                topic,
                content,
                relevance,
                len(self._items),
            )
            return item

    def add_finding(self, topic: str, content: str, **kwargs: Any) -> MemoryItem:
        """Shortcut: add a finding."""
        return self.add(topic, content, item_type="finding", **kwargs)

    def add_gap(self, topic: str, content: str, **kwargs: Any) -> MemoryItem:
        """Shortcut: add a knowledge gap."""
        return self.add(topic, content, item_type="gap", relevance=0.95, **kwargs)

    def add_insight(self, topic: str, content: str, **kwargs: Any) -> MemoryItem:
        """Shortcut: add a synthesized insight."""
        return self.add(topic, content, item_type="insight", relevance=0.9, **kwargs)

    def add_plan(self, topic: str, content: str, **kwargs: Any) -> MemoryItem:
        """Shortcut: add a plan fragment."""
        return self.add(topic, content, item_type="plan", relevance=0.85, **kwargs)

    def add_error(self, topic: str, content: str, **kwargs: Any) -> MemoryItem:
        """Shortcut: add an error record."""
        return self.add(topic, content, item_type="error", relevance=0.8, **kwargs)

    # ── Focus management ──────────────────────────────────────────────

    def set_focus(self, topic: str) -> None:
        """Set the current topic focus.

        Items for the focused topic get a relevance boost; others decay.
        """
        with tracer.start_as_current_span("working_memory.set_focus"):
            previous = self._current_topic
            self._current_topic = topic
            self._focus_counts[topic] += 1

            if previous and previous != topic:
                logger.info("WM focus shift: %s → %s", previous, topic)
                self._apply_decay(boost_topic=topic)
            elif previous is None:
                logger.info("WM initial focus: %s", topic)

    def _apply_decay(self, boost_topic: str) -> None:
        """Decay relevance for off-topic items, boost on-topic items."""
        for item in self._items:
            if item.topic == boost_topic:
                # Boost items for the newly focused topic (cap at 1.0)
                item.relevance = min(item.relevance * 1.1, 1.0)
            else:
                # Decay items for other topics
                item.relevance *= self._decay_factor

        # Remove items that have decayed below threshold
        before = len(self._items)
        self._items = [i for i in self._items if i.relevance > 0.05]
        evicted = before - len(self._items)
        if evicted > 0:
            logger.debug("WM decay evicted %d items (below 0.05 relevance)", evicted)

    def tick(self) -> None:
        """Called once per loop iteration to apply passive decay."""
        with tracer.start_as_current_span("working_memory.tick"):
            for item in self._items:
                if self._current_topic and item.topic != self._current_topic:
                    item.relevance *= self._decay_factor
            self._items = [i for i in self._items if i.relevance > 0.05]
            self._enforce_capacity()

    # ── Querying ──────────────────────────────────────────────────────

    def get_context(self, topic: str | None = None, max_items: int = 20) -> list[MemoryItem]:
        """Get the most relevant items, optionally filtered by topic."""
        items = self._items
        if topic:
            items = [i for i in items if i.topic == topic]
        sorted_items = sorted(items, key=lambda i: i.relevance, reverse=True)
        return sorted_items[:max_items]

    def get_gaps(self, topic: str | None = None) -> list[MemoryItem]:
        """Get all gap items for a topic."""
        items = self._items if not topic else [i for i in self._items if i.topic == topic]
        return [i for i in items if i.item_type == "gap"]

    def get_insights(self, topic: str | None = None) -> list[MemoryItem]:
        """Get all insight items for a topic."""
        items = self._items if not topic else [i for i in self._items if i.topic == topic]
        return [i for i in items if i.item_type == "insight"]

    def get_errors(self, topic: str | None = None) -> list[MemoryItem]:
        """Get all error items for a topic."""
        items = self._items if not topic else [i for i in self._items if i.topic == topic]
        return [i for i in items if i.item_type == "error"]

    def get_all_topics(self) -> set[str]:
        """Return all topics currently in working memory."""
        return {i.topic for i in self._items}

    @property
    def size(self) -> int:
        return len(self._items)

    # ── Context serialisation for LLM prompts ─────────────────────────

    def build_prompt_context(self, topic: str, max_tokens_approx: int = 2000) -> str:
        """Build a context string suitable for injection into an LLM prompt.

        Groups items by type and presents the most relevant ones within an
        approximate token budget (rough: 1 token ≈ 4 chars).
        """
        with tracer.start_as_current_span("working_memory.build_prompt_context"):
            max_chars = max_tokens_approx * 4
            items = self.get_context(topic=topic, max_items=30)
            if not items:
                return f"No working memory for topic '{topic}'."

            sections: dict[str, list[str]] = defaultdict(list)
            for item in items:
                label = item.item_type.upper()
                sections[label].append(
                    f"  - [{item.relevance:.2f}] {item.content}"
                )

            lines: list[str] = [f"=== Working Memory: {topic} ==="]

            # Priority order for sections
            section_order = ["GAP", "PLAN", "INSIGHT", "FINDING", "ERROR"]
            for section in section_order:
                if section in sections:
                    lines.append(f"\n[{section}S]")
                    lines.extend(sections[section])

            # Also include any unlisted types
            for section, entries in sections.items():
                if section not in section_order:
                    lines.append(f"\n[{section}S]")
                    lines.extend(entries)

            # Add topic summary if available
            if topic in self._topic_summaries:
                lines.insert(1, f"Summary: {self._topic_summaries[topic]}")

            text = "\n".join(lines)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return text

    def set_topic_summary(self, topic: str, summary: str) -> None:
        """Set a high-level summary for a topic (persists across decays)."""
        self._topic_summaries[topic] = summary

    # ── Capacity management ───────────────────────────────────────────

    def _enforce_capacity(self) -> None:
        """Evict lowest-relevance items when over capacity."""
        if len(self._items) <= self._max_items:
            return
        self._items.sort(key=lambda i: i.relevance, reverse=True)
        evicted = self._items[self._max_items :]
        self._items = self._items[: self._max_items]
        logger.debug(
            "WM capacity enforced: evicted %d items (lowest relevance: %.3f)",
            len(evicted),
            evicted[-1].relevance if evicted else 0,
        )

    def clear(self, topic: str | None = None) -> int:
        """Clear items, optionally for a specific topic."""
        before = len(self._items)
        if topic:
            self._items = [i for i in self._items if i.topic != topic]
            self._topic_summaries.pop(topic, None)
        else:
            self._items.clear()
            self._topic_summaries.clear()
        removed = before - len(self._items)
        logger.info("WM cleared %d items (topic=%s)", removed, topic or "all")
        return removed

    def snapshot(self) -> dict[str, Any]:
        """Return a serialisable snapshot of working memory state."""
        return {
            "total_items": len(self._items),
            "current_topic": self._current_topic,
            "topics": list(self.get_all_topics()),
            "items_by_type": {
                t: len([i for i in self._items if i.item_type == t])
                for t in {i.item_type for i in self._items}
            },
            "focus_counts": dict(self._focus_counts),
            "topic_summaries": dict(self._topic_summaries),
        }
