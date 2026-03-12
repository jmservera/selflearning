# Orchestrator Service

Drives the learning pipeline — decides what to learn next.

## Responsibilities

- Consume evaluation reports from `evaluation-complete` Service Bus topic
- Accept user-initiated topic requests via the API Gateway
- Implement the learning loop: Evaluate → Plan → Scrape → Extract → Organize → Reason → Evaluate
- Prioritize learning actions based on gap severity and topic importance
- Manage concurrent learning across multiple topics
- Implement backoff and circuit-breaking for failing pipelines
- Publish scrape requests and reasoning requests

## Self-Improvement Logic

1. **Gap-driven learning** — Evaluation gaps become scrape targets
2. **Confidence boosting** — Low-confidence claims trigger verification scraping
3. **Source diversification** — If too few sources, diversify targets
4. **Depth escalation** — Once breadth exceeds threshold, shift to depth

## Azure Dependencies

- Azure Service Bus (topic subscriber + queue publisher)
- Azure Cosmos DB (pipeline state, topic configuration)
- Azure AI Foundry (query generation for targeted scraping)

## Running Locally

```bash
pip install -r requirements.txt
python -m orchestrator
```
