@description('Location for all resources')
param location string

@description('Unique token for resource naming')
param resourceToken string

@description('Tags for all resources')
param tags object

var abbrs = loadJsonContent('../abbreviations.json')

resource aiSearch 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: '${abbrs.aiSearch}${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    semanticSearch: 'standard'
  }
}

output aiSearchId string = aiSearch.id
output aiSearchName string = aiSearch.name
output endpoint string = 'https://${aiSearch.name}.search.windows.net'
