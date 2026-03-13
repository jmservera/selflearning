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

resource topicsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'topics'
  properties: {
    resource: {
      id: 'topics'
      partitionKey: {
        paths: ['/topic']
        kind: 'Hash'
        version: 2
      }
    }
  }
}

resource strategiesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'strategies'
  properties: {
    resource: {
      id: 'strategies'
      partitionKey: {
        paths: ['/topic']
        kind: 'Hash'
        version: 2
      }
    }
  }
}

resource crawlHistoryContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'crawl-history'
  properties: {
    resource: {
      id: 'crawl-history'
      partitionKey: {
        paths: ['/url']
        kind: 'Hash'
        version: 2
      }
      defaultTtl: 2592000 // 30 days for crawl history
    }
  }
}

output accountId string = cosmosAccount.id
output accountName string = cosmosAccount.name
output endpoint string = cosmosAccount.properties.documentEndpoint
