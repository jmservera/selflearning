# Extractor Service

Transforms raw scraped content into structured knowledge units.

## Responsibilities

- Consume raw content references from the `scrape-complete` Service Bus topic
- Use Azure AI Foundry LLMs for entity extraction, relationship identification, and claim extraction
- Generate embeddings for semantic similarity
- Produce typed knowledge units: Entity, Relationship, Claim, Summary
- Attach provenance metadata (source URL, confidence, timestamp)
- Publish structured units to the `extraction-complete` Service Bus topic

## Extraction Pipeline

1. **Chunk** — Split long documents with overlap
2. **Extract entities** — Named entities, concepts, definitions
3. **Extract relationships** — How entities relate to each other
4. **Extract claims** — Factual assertions with confidence scores
5. **Summarize** — Per-chunk and full-document summaries
6. **Embed** — Generate vector embeddings for all units

## Azure Dependencies

- Azure Service Bus (topic subscriber + topic publisher)
- Azure Blob Storage (read raw content)
- Azure AI Foundry (LLM inference, embedding generation)

## Running Locally

```bash
pip install -r pyproject.toml
python -m extractor
```
