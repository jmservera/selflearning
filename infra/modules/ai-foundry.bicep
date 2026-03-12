@description('Location for all resources')
param location string

@description('Unique token for resource naming')
param resourceToken string

@description('Tags for all resources')
param tags object

@description('Key Vault resource ID for AI Foundry connection')
param keyVaultId string

@description('Storage Account resource ID for AI Foundry connection')
param storageAccountId string

@description('AI Search resource ID for AI Foundry connection')
param aiSearchId string

@description('Whether to deploy GPT model')
param deployGptModel bool = true

@description('Whether to deploy embedding model')
param deployEmbeddingModel bool = true

var abbrs = loadJsonContent('../abbreviations.json')

// AI Foundry Account (hub-level resource)
resource aiFoundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${abbrs.aiFoundryAccount}${resourceToken}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${abbrs.aiFoundryAccount}${resourceToken}'
    publicNetworkAccess: 'Enabled'
  }
}

// GPT-4o deployment
resource gptDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' =
  if (deployGptModel) {
    name: 'gpt-4o'
    parent: aiFoundryAccount
    sku: {
      name: 'GlobalStandard'
      capacity: 30
    }
    properties: {
      model: {
        format: 'OpenAI'
        name: 'gpt-4o'
        version: '2024-11-20'
      }
    }
  }

// Embedding model deployment
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' =
  if (deployEmbeddingModel) {
    name: 'text-embedding-3-large'
    parent: aiFoundryAccount
    sku: {
      name: 'Standard'
      capacity: 30
    }
    properties: {
      model: {
        format: 'OpenAI'
        name: 'text-embedding-3-large'
        version: '1'
      }
    }
    dependsOn: [gptDeployment]
  }

output accountId string = aiFoundryAccount.id
output accountName string = aiFoundryAccount.name
output projectEndpoint string = aiFoundryAccount.properties.endpoint
