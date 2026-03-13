@description('Location for all resources')
param location string

@description('Unique token for resource naming')
param resourceToken string

@description('Tags for all resources')
param tags object

@description('Cosmos DB account name for RBAC')
param cosmosDbAccountName string

@description('Service Bus namespace name for RBAC')
param serviceBusNamespaceName string

@description('Storage account name for RBAC')
param storageAccountName string

@description('Key Vault name for RBAC')
param keyVaultName string

@description('AI Search name for RBAC')
param aiSearchName string

@description('AI Foundry account name for RBAC')
param aiFoundryAccountName string

var abbrs = loadJsonContent('../abbreviations.json')

// Shared managed identity for all services
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${abbrs.managedIdentity}${resourceToken}'
  location: location
  tags: tags
}

// --- RBAC Role Assignments ---

// Cosmos DB Data Contributor
resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosDbAccountName
}

resource cosmosDbRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosDbAccount
  // Use a deterministic GUID based on identity + role
  name: guid(cosmosDbAccount.id, managedIdentity.id, '00000000-0000-0000-0000-000000000002')
  properties: {
    roleDefinitionId: '${cosmosDbAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002' // Built-in Data Contributor
    principalId: managedIdentity.properties.principalId
    scope: cosmosDbAccount.id
  }
}

// Service Bus Data Owner
resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' existing = {
  name: serviceBusNamespaceName
}

resource serviceBusRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBusNamespace.id, managedIdentity.id, '090c5cfd-751d-490a-894a-3ce6f1109419')
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '090c5cfd-751d-490a-894a-3ce6f1109419'
    ) // Azure Service Bus Data Owner
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Blob Data Contributor
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource storageBlobRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    ) // Storage Blob Data Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Key Vault Secrets User
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, '4633458b-17de-408a-b874-0445c86b69e6')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'
    ) // Key Vault Secrets User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// AI Search Index Data Contributor
resource aiSearch 'Microsoft.Search/searchServices@2024-03-01-preview' existing = {
  name: aiSearchName
}

resource aiSearchRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiSearch.id, managedIdentity.id, '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  scope: aiSearch
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
    ) // Search Index Data Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// AI Foundry — Cognitive Services OpenAI User
resource aiFoundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiFoundryAccountName
}

resource aiFoundryRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiFoundryAccount.id, managedIdentity.id, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  scope: aiFoundryAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
    ) // Cognitive Services OpenAI User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Healer — Container Apps management (Contributor on resource group)
resource healerContainerAppsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, managedIdentity.id, 'b24988ac-6180-42a0-ab88-20f7382dd24c', 'healer-ca-mgmt')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'b24988ac-6180-42a0-ab88-20f7382dd24c'
    ) // Contributor — needed by healer to restart/scale Container Apps
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    description: 'Healer service: Container Apps restart and scale management'
  }
}

output identityId string = managedIdentity.id
output identityClientId string = managedIdentity.properties.clientId
output identityPrincipalId string = managedIdentity.properties.principalId
output identityName string = managedIdentity.name
