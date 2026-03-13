# Dozer — History

## Project Context

- **Project:** selflearning — A self-healing, self-improving AI system (Python/FastAPI microservices, Azure Cosmos DB, AI Search, Service Bus)
- **Owner:** jmservera
- **Stack:** Python FastAPI (8 backend services + 1 JS/nginx UI), Azure Container Apps, ACR, Bicep IaC, azd CLI
- **Services:** api, scraper, extractor, knowledge, reasoner, evaluator, orchestrator, healer, ui
- **Infra:** Bicep modules in `infra/`, ACR (Basic SKU), Container Apps with managed identity
- **Docker:** 9 Dockerfiles in `src/{service}/Dockerfile`, docker-compose.yml for local dev
- **Existing ACR Bicep:** `infra/modules/container-registry.bicep` — Basic SKU, admin disabled
- **Container App image pattern:** `{acr-login-server}/selflearning-{service}:latest`

## Learnings

### Remote ACR Builds (2025-03-13)
- **Pattern:** Use `az acr build` for remote container builds — no local Docker required
- **Script location:** `scripts/acr-build.sh` — builds all or specific services remotely
- **ACR discovery:** ACR name is retrieved from `azd env get-values | grep AZURE_CONTAINER_REGISTRY_NAME`
- **Image naming:** `selflearning-{service}:latest` and `selflearning-{service}:{git-sha}` (matches container-app.bicep)
- **CI/CD workflow:** `.github/workflows/acr-build.yml` — auto-builds changed services on push to main
- **Authentication:** GitHub Actions uses OIDC (federated credentials) — no secrets needed
- **Change detection:** Workflow detects changed services by diffing `src/**` paths, builds only what changed
- **Manual trigger:** `workflow_dispatch` input allows building all or specific services
- **User preference:** jmservera wants to eliminate local Docker dependency — ACR Tasks achieves this
- **Build tags:** Always tag with both `latest` (for Container Apps) and git SHA (for traceability)
- **Error handling:** Script validates azd environment, Azure login, service names before building
