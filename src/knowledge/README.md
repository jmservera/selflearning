# Knowledge Service

Manages the knowledge graph — the system's accumulated expertise.

## Responsibilities

- Consume structured knowledge units from the `extraction-complete` Service Bus topic
- Merge new knowledge into the graph (entity resolution, deduplication)
- Maintain vector embeddings in Azure AI Search
- Track knowledge provenance and confidence scores
- Detect contradictions between knowledge units
- Expose internal HTTP API for graph queries (used by Reasoner, Evaluator, API Gateway)

## Knowledge Graph Schema

See `docs/architecture.md` Section 6 for the full schema.

Document types: Entity, Relationship, Claim, Source

Partition key: `topic` (co-locates all knowledge for a topic)

## Azure Dependencies

- Azure Cosmos DB (knowledge graph storage)
- Azure AI Search (vector index for semantic search)
- Azure Service Bus (topic subscriber)
- Azure AI Foundry (embedding generation for new entities)

## Running Locally

```bash
pip install -r pyproject.toml
python -m knowledge
```
