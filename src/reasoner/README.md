# Reasoner Service

Synthesizes knowledge, identifies gaps, and generates insights.

## Responsibilities

- Consume reasoning requests from the `reasoning-requests` Service Bus queue
- Perform multi-step reasoning over the knowledge graph (chain-of-thought, tree-of-thought)
- Use RAG over the knowledge graph for grounded reasoning
- Identify knowledge gaps (topics with thin coverage or low confidence)
- Resolve contradictions by weighing source authority and recency
- Generate higher-order conclusions from atomic knowledge
- Publish insights and gap reports to `reasoning-complete` Service Bus topic

## Reasoning Strategies

1. **Gap analysis** — Find topics with low entity count or confidence
2. **Contradiction resolution** — Weigh conflicting claims
3. **Synthesis** — Combine atomic knowledge into insights
4. **Depth probing** — Follow citation chains for primary sources

## Azure Dependencies

- Azure Service Bus (queue consumer + topic publisher)
- Azure Cosmos DB (via Knowledge Service API)
- Azure AI Search (via Knowledge Service API)
- Azure AI Foundry (LLM reasoning chains)

## Running Locally

```bash
pip install -r pyproject.toml
python -m reasoner
```
