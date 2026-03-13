@description('Key Vault name where secrets will be stored')
param keyVaultName string

@description('Application Insights connection string to store as a secret')
@secure()
param appInsightsConnectionString string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource appInsightsSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'applicationinsights-connection-string'
  properties: {
    value: appInsightsConnectionString
  }
}

output appInsightsSecretUri string = appInsightsSecret.properties.secretUri
