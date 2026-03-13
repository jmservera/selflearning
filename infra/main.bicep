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

@description('Use a placeholder public image for the very first azd provision before any images are pushed to ACR. Set to true on first deployment; leave false for steady-state re-provisions.')
param useDefaultImage bool = false

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
    aiFoundryAccountName: aiFoundry.outputs.accountName
    containerRegistryName: containerRegistry.outputs.registryName
  }
}

// Key Vault Secrets — store sensitive config values for Container Apps secret references
module keyVaultSecrets 'modules/key-vault-secrets.bicep' = {
  name: 'key-vault-secrets'
  scope: rg
  params: {
    keyVaultName: keyVault.outputs.keyVaultName
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
  }
}

// Shared secrets — Key Vault-backed, mounted into every backend container app
var sharedSecrets = [
  {
    name: 'appinsights-connection-string'
    kvSecretName: 'applicationinsights-connection-string'
  }
]

// Shared env vars common to all backend services
var backendEnv = [
  { name: 'AZURE_AI_FOUNDRY_ENDPOINT', value: aiFoundry.outputs.projectEndpoint }
  { name: 'AZURE_COSMOS_ENDPOINT', value: cosmosDb.outputs.endpoint }
  { name: 'AZURE_SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
  { name: 'AZURE_STORAGE_ACCOUNT', value: storage.outputs.storageAccountName }
  { name: 'AZURE_SEARCH_ENDPOINT', value: aiSearch.outputs.endpoint }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
  { name: 'AZURE_CLIENT_ID', value: identity.outputs.identityClientId }
]

// --- Container Apps — one per backend service ---

module caScraperApp 'modules/container-app.bicep' = {
  name: 'ca-scraper'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'scraper'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: false
    minReplicas: 0
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'SCRAPER_SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
      { name: 'SCRAPER_BLOB_ACCOUNT_URL', value: storage.outputs.blobEndpoint }
      { name: 'SCRAPER_COSMOS_ENDPOINT', value: cosmosDb.outputs.endpoint }
    ])
    serviceBusNamespace: serviceBus.outputs.fullyQualifiedNamespace
    serviceBusQueueName: 'scrape-requests'
    scaleIdentityId: identity.outputs.identityId
    kedaMessageCount: 20
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

module caExtractorApp 'modules/container-app.bicep' = {
  name: 'ca-extractor'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'extractor'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: false
    minReplicas: 0
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
      { name: 'STORAGE_ACCOUNT_URL', value: storage.outputs.blobEndpoint }
      { name: 'AZURE_AI_ENDPOINT', value: aiFoundry.outputs.projectEndpoint }
    ])
    serviceBusNamespace: serviceBus.outputs.fullyQualifiedNamespace
    serviceBusTopicName: 'scrape-complete'
    serviceBusSubscriptionName: 'extractor'
    scaleIdentityId: identity.outputs.identityId
    kedaMessageCount: 20
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

module caKnowledgeApp 'modules/container-app.bicep' = {
  name: 'ca-knowledge'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'knowledge'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: false
    minReplicas: 0
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'COSMOS_CONTAINER_NAME', value: 'knowledge' }
      { name: 'SEARCH_INDEX_PREFIX', value: 'selflearning' }
    ])
    serviceBusNamespace: serviceBus.outputs.fullyQualifiedNamespace
    serviceBusTopicName: 'extraction-complete'
    serviceBusSubscriptionName: 'knowledge-service'
    scaleIdentityId: identity.outputs.identityId
    kedaMessageCount: 20
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

module caReasonerApp 'modules/container-app.bicep' = {
  name: 'ca-reasoner'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'reasoner'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: false
    minReplicas: 0
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
      { name: 'AZURE_AI_ENDPOINT', value: aiFoundry.outputs.projectEndpoint }
      {
        name: 'KNOWLEDGE_SERVICE_URL'
        value: 'https://ca-knowledge.${containerAppsEnv.outputs.defaultDomain}'
      }
    ])
    serviceBusNamespace: serviceBus.outputs.fullyQualifiedNamespace
    serviceBusQueueName: 'reasoning-requests'
    scaleIdentityId: identity.outputs.identityId
    kedaMessageCount: 10
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

module caEvaluatorApp 'modules/container-app.bicep' = {
  name: 'ca-evaluator'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'evaluator'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: false
    minReplicas: 0
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'COSMOS_ENDPOINT', value: cosmosDb.outputs.endpoint }
      {
        name: 'KNOWLEDGE_SERVICE_URL'
        value: 'https://ca-knowledge.${containerAppsEnv.outputs.defaultDomain}'
      }
    ])
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

module caOrchestratorApp 'modules/container-app.bicep' = {
  name: 'ca-orchestrator'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'orchestrator'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: false
    minReplicas: 1
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'ORCHESTRATOR_SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
      { name: 'ORCHESTRATOR_AI_FOUNDRY_ENDPOINT', value: aiFoundry.outputs.projectEndpoint }
      { name: 'ORCHESTRATOR_COSMOS_ENDPOINT', value: cosmosDb.outputs.endpoint }
      { name: 'ORCHESTRATOR_SUBSCRIPTION_NAME', value: 'orchestrator-sub' }
      {
        name: 'ORCHESTRATOR_SCRAPER_URL'
        value: 'https://ca-scraper.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'ORCHESTRATOR_EXTRACTOR_URL'
        value: 'https://ca-extractor.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'ORCHESTRATOR_KNOWLEDGE_URL'
        value: 'https://ca-knowledge.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'ORCHESTRATOR_REASONER_URL'
        value: 'https://ca-reasoner.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'ORCHESTRATOR_EVALUATOR_URL'
        value: 'https://ca-evaluator.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'ORCHESTRATOR_HEALER_URL'
        value: 'https://ca-healer.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'ORCHESTRATOR_API_URL'
        value: 'https://ca-api.${containerAppsEnv.outputs.defaultDomain}'
      }
    ])
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

module caHealerApp 'modules/container-app.bicep' = {
  name: 'ca-healer'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'healer'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: false
    minReplicas: 1
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'HEALER_SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
      { name: 'HEALER_AI_FOUNDRY_ENDPOINT', value: aiFoundry.outputs.projectEndpoint }
      { name: 'HEALER_SUBSCRIPTION_ID', value: subscription().subscriptionId }
      { name: 'HEALER_RESOURCE_GROUP', value: rg.name }
      { name: 'HEALER_CONTAINER_APP_ENV', value: containerAppsEnv.outputs.environmentName }
      {
        name: 'HEALER_SCRAPER_URL'
        value: 'https://ca-scraper.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'HEALER_EXTRACTOR_URL'
        value: 'https://ca-extractor.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'HEALER_KNOWLEDGE_URL'
        value: 'https://ca-knowledge.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'HEALER_REASONER_URL'
        value: 'https://ca-reasoner.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'HEALER_EVALUATOR_URL'
        value: 'https://ca-evaluator.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'HEALER_ORCHESTRATOR_URL'
        value: 'https://ca-orchestrator.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'HEALER_API_URL'
        value: 'https://ca-api.${containerAppsEnv.outputs.defaultDomain}'
      }
    ])
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

module caApiApp 'modules/container-app.bicep' = {
  name: 'ca-api'
  scope: rg
  params: {
    location: location
    tags: tags
    serviceName: 'api'
    containerAppsEnvironmentId: containerAppsEnv.outputs.environmentId
    containerRegistryLoginServer: containerRegistry.outputs.loginServer
    identityId: identity.outputs.identityId
    identityClientId: identity.outputs.identityClientId
    external: true
    minReplicas: 1
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: concat(backendEnv, [
      { name: 'AZURE_SERVICEBUS_NAMESPACE', value: serviceBus.outputs.fullyQualifiedNamespace }
      {
        name: 'KNOWLEDGE_SERVICE_URL'
        value: 'https://ca-knowledge.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'ORCHESTRATOR_SERVICE_URL'
        value: 'https://ca-orchestrator.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'EVALUATOR_SERVICE_URL'
        value: 'https://ca-evaluator.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'HEALER_SERVICE_URL'
        value: 'https://ca-healer.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'SCRAPER_SERVICE_URL'
        value: 'https://ca-scraper.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'EXTRACTOR_SERVICE_URL'
        value: 'https://ca-extractor.${containerAppsEnv.outputs.defaultDomain}'
      }
      {
        name: 'REASONER_SERVICE_URL'
        value: 'https://ca-reasoner.${containerAppsEnv.outputs.defaultDomain}'
      }
    ])
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

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
    minReplicas: 1
    keyVaultUri: keyVault.outputs.keyVaultUri
    secrets: sharedSecrets
    env: [
      { name: 'API_GATEWAY_URL', value: 'https://${caApiApp.outputs.fqdn}' }
      { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
    ]
    useDefaultImage: useDefaultImage
  }
  dependsOn: [keyVaultSecrets]
}

// Outputs for azd
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_AI_FOUNDRY_ENDPOINT string = aiFoundry.outputs.projectEndpoint
output AZURE_COSMOS_ENDPOINT string = cosmosDb.outputs.endpoint
output AZURE_SERVICEBUS_NAMESPACE string = serviceBus.outputs.fullyQualifiedNamespace
output AZURE_STORAGE_ACCOUNT string = storage.outputs.storageAccountName
output AZURE_SEARCH_ENDPOINT string = aiSearch.outputs.endpoint
output API_GATEWAY_URL string = 'https://${caApiApp.outputs.fqdn}'
output UI_URL string = 'https://${uiContainerApp.outputs.fqdn}'
