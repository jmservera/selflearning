# Tests

Integration and end-to-end tests for the selflearning system.

## Structure (planned)

```
tests/
├── integration/           # Service-to-service integration tests
│   ├── test_scrape_pipeline.py
│   ├── test_extraction_pipeline.py
│   └── test_knowledge_merge.py
├── e2e/                   # Full pipeline end-to-end tests
│   └── test_learning_loop.py
└── conftest.py            # Shared fixtures (Azure emulators, test data)
```

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

## Test Strategy

- **Unit tests** live inside each service's directory (`src/<service>/tests/`)
- **Integration tests** verify service-to-service communication via Service Bus
- **E2E tests** run a full learning cycle on a small topic and verify knowledge accumulation
