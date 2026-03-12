# Healer Service

Monitors system health, detects failures, and triggers recovery.

## Responsibilities

- Monitor Azure Monitor metrics, Application Insights traces, and Service Bus dead-letter queues
- Replay failed messages from dead-letter queues with backoff
- Trigger Container App revision restarts for degraded services
- Adjust scaling rules based on load patterns
- Re-route around degraded AI Foundry model endpoints
- Analyze failure patterns to suggest pipeline improvements
- Tune extraction prompts based on quality metrics
- Report health status to API Gateway

## Self-Healing Layers

1. **Infrastructure** — Container Apps auto-restart, KEDA scaling (Azure-native)
2. **Pipeline** — DLQ processing, circuit breaking, endpoint failover
3. **Cognitive** — Prompt tuning, learning strategy adjustment, knowledge refresh

## Azure Dependencies

- Azure Monitor / Application Insights (health signals)
- Azure Service Bus (DLQ monitoring, event consumer)
- Azure Container Apps Management API (restart, scale)
- Azure AI Foundry (model health checks)

## Running Locally

```bash
pip install -r pyproject.toml
python -m healer
```
