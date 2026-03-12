# Scraper Service

Discovers and retrieves content from the internet for knowledge acquisition.

## Responsibilities

- Accept scrape requests from the `scrape-requests` Service Bus queue
- Execute web searches and fetch pages (HTML, PDF, API responses)
- Respect robots.txt and rate limits
- Deduplicate URLs against Cosmos DB crawl history
- Store raw content in Azure Blob Storage
- Publish completion events to the `scrape-complete` Service Bus topic

## Source Adapters (planned)

- Web search (Bing API)
- Academic APIs (Semantic Scholar, arXiv)
- RSS feeds
- Social media APIs

## Azure Dependencies

- Azure Service Bus (queue consumer + topic publisher)
- Azure Blob Storage (raw content output)
- Azure Cosmos DB (crawl history)
- Azure AI Foundry (optional: LLM-guided query generation)

## Running Locally

```bash
pip install -r requirements.txt
python -m scraper
```
