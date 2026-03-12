targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (e.g., dev, staging, prod)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('AI Foundry model deployments configuration')
param deployGptModel bool = true
param deployEmbeddingModel bool = true

// Generate resource name prefix
var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
  project: 'selflearning'
}

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: '${abbrs.resourceGroup}${environmentName}'
  location: location
  tags: tags
}

// Monitoring (deploy first — other modules reference Log Analytics and App Insights)
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// Key Vault
module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// Storage Account
module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// Cosmos DB
module cosmosDb 'modules/cosmos-db.bicep' = {
  name: 'cosmos-db'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// AI Search
module aiSearch 'modules/ai-search.bicep' = {
  name: 'ai-search'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// Service Bus
module serviceBus 'modules/service-bus.bicep' = {
  name: 'service-bus'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// Container Registry
module containerRegistry 'modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// AI Foundry
module aiFoundry 'modules/ai-foundry.bicep' = {
  name: 'ai-foundry'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    keyVaultId: keyVault.outputs.keyVaultId
    storageAccountId: storage.outputs.storageAccountId
    aiSearchId: aiSearch.outputs.aiSearchId
    deployGptModel: deployGptModel
    deployEmbeddingModel: deployEmbeddingModel
  }
}

// Container Apps Environment
module containerAppsEnv 'modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsWorkspaceName
  }
}

// Managed Identities and RBAC
module identity 'modules/identity.bicep' = {
  name: 'identity'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    cosmosDbAccountName: cosmosDb.outputs.accountName
    serviceBusNamespaceName: serviceBus.outputs.namespaceName
    storageAccountName: storage.outputs.storageAccountName
    keyVaultName: keyVault.outputs.keyVaultName
    aiSearchName: aiSearch.outputs.aiSearchName
  }
}

// Container Apps — backend services (Python, port 8000)
var backendServices = [
  { name: 'scraper', external: false }
  { name: 'extractor', external: false }
  { name: 'knowledge', external: false }
  { name: 'reasoner', external: false }
  { name: 'evaluator', external: false }
  { name: 'orchestrator', external: false }
  { name: 'healer', external: false }
  { name: 'api', external: true }
]

var backendEnv = [
  { name: 'AZURE_AI_FOUNDRY_ENDPOINT', value: aiFoundry.outputs.projectEndpoint }
  { name: 'AZURE_COSMOS_ENDPOINT', value: cosmosDb.outputs.endpoint }
  { name: 'AZURE_SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
  { name: 'AZURE_STORAGE_ACCOUNT', value: storage.outputs.storageAccountName }
  { name: 'AZURE_SEARCH_ENDPOINT', value: aiSearch.outputs.endpoint }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: monitoring.outputs.appInsightsConnectionString
  }
  { name: 'AZURE_CLIENT_ID', value: identity.outputs.identityClientId }
]

module containerApps 'modules/container-app.bicep' = [
  for service in backendServices: {
    name: 'ca-${service.name}'
    scope: rg
    params: {
      location: location
      tags: tags
      serviceName: service.name
      containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
      containerRegistryLoginServer: containerRegistry.outputs.loginServer
      identityId: identity.outputs.identityId
      identityClientId: identity.outputs.identityClientId
      external: service.external
      env: backendEnv
    }
  }
]

// UI Container App (nginx, port 80)
module uiContainerApp 'modules/container-app.bicep' = {
  name: 'ca-ui'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'ui'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: true
    targetPort: 80
    env: [
      { name: 'API_GATEWAY_URL', value: 'https://${containerApps[7].outputs.fqdn}' }
    ]
  }
}

// Outputs for azd
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_AI_FOUNDRY_ENDPOINT string = aiFoundry.outputs.projectEndpoint
output AZURE_COSMOS_ENDPOINT string = cosmosDb.outputs.endpoint
output AZURE_SERVICEBUS_NAMESPACE string = serviceBus.outputs.fullyQualifiedNamespace
output AZURE_STORAGE_ACCOUNT string = storage.outputs.storageAccountName
output AZURE_SEARCH_ENDPOINT string = aiSearch.outputs.endpoint
output API_GATEWAY_URL string = 'https://${containerApps[7].outputs.fqdn}'
output UI_URL string = 'https://${uiContainerApp.outputs.fqdn}'
