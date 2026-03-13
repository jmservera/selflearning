@description('Location for all resources')
param location string

@description('Unique token for resource naming')
param resourceToken string

@description('Tags for all resources')
param tags object

var abbrs = loadJsonContent('../abbreviations.json')

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: '${abbrs.cosmosDbAccount}${resourceToken}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: false
    capabilities: [
      { name: 'EnableServerless' }
    ]
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: 'selflearning'
  properties: {
    resource: {
      id: 'selflearning'
    }
  }
}

resource entitiesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'knowledge'
  properties: {
    resource: {
      id: 'knowledge'
      partitionKey: {
        paths: ['/topic']
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        includedPaths: [
          { path: '/*' }
        ]
        excludedPaths: [
          { path: '/embedding/*' }
          { path: '/"_etag"/?' }
        ]
      }
    }
  }
}

resource sourcesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'sources'
  properties: {
    resource: {
      id: 'sources'
      partitionKey: {
        paths: ['/topic']
        kind: 'Hash'
        version: 2
      }
    }
  }
}

resource pipelineContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'pipeline-state'
  properties: {
    resource: {
      id: 'pipeline-state'
      partitionKey: {
        paths: ['/topic']
        kind: 'Hash'
        version: 2
      }
      defaultTtl: 604800 // 7 days for transient pipeline state
    }
  }
}

resource evaluationsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'evaluations'
  properties: {
    resource: {
      id: 'evaluations'
      partitionKey: {
        paths: ['/topic']
        kind: 'Hash'
        version: 2
      }
    }
  }
}

output accountId string = cosmosAccount.id
output accountName string = cosmosAccount.name
output endpoint string = cosmosAccount.properties.documentEndpoint
