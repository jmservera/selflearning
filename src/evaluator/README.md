# Evaluator Service

Measures the system's expertise level and identifies weaknesses.

## Responsibilities

- Run on schedule and after reasoning cycles
- Generate benchmark questions (PhD-qualifying-exam style)
- Self-test using RAG over the knowledge graph
- Compare knowledge coverage against authoritative taxonomies
- Produce expertise scorecards (coverage %, confidence distribution, gap inventory)
- Track expertise trajectory over time
- Publish evaluation reports to `evaluation-complete` Service Bus topic

## Evaluation Approaches

1. **Taxonomy coverage** — Compare graph entities against known topic taxonomies
2. **Self-testing** — Generate and answer questions using only the knowledge graph
3. **Authority comparison** — Compare claims against authoritative sources

## Azure Dependencies

- Azure Service Bus (topic publisher)
- Azure Cosmos DB (via Knowledge Service API)
- Azure AI Search (via Knowledge Service API)
- Azure AI Foundry (LLM-as-judge, question generation)

## Running Locally

```bash
pip install -r pyproject.toml
python -m evaluator
```
