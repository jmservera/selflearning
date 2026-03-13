@description('Location for all resources')
param location string

@description('Unique token for resource naming')
param resourceToken string

@description('Tags for all resources')
param tags object

var abbrs = loadJsonContent('../abbreviations.json')

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: '${abbrs.serviceBusNamespace}${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
}

// Queues (point-to-point)
resource scrapeRequestsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'scrape-requests'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
  }
}

resource reasoningRequestsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'reasoning-requests'
  properties: {
    maxDeliveryCount: 3
    deadLetteringOnMessageExpiration: true
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
  }
}

// Topics (pub/sub)
resource scrapeCompleteTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'scrape-complete'
  properties: {
    defaultMessageTimeToLive: 'P1D'
  }
}

resource scrapeCompleteExtractorSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: scrapeCompleteTopic
  name: 'extractor'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M'
  }
}

resource scrapeCompleteOrchestratorSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: scrapeCompleteTopic
  name: 'orchestrator-sub'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M'
  }
}

resource extractionCompleteTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'extraction-complete'
  properties: {
    defaultMessageTimeToLive: 'P1D'
  }
}

resource extractionCompleteKnowledgeSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: extractionCompleteTopic
  name: 'knowledge-service'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M'
  }
}

resource extractionCompleteOrchestratorSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: extractionCompleteTopic
  name: 'orchestrator-sub'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M'
  }
}

resource reasoningCompleteTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'reasoning-complete'
  properties: {
    defaultMessageTimeToLive: 'P1D'
  }
}

resource reasoningCompleteOrchestratorSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: reasoningCompleteTopic
  name: 'orchestrator-sub'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M'
  }
}

resource evaluationCompleteTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'evaluation-complete'
  properties: {
    defaultMessageTimeToLive: 'P1D'
  }
}

resource evaluationCompleteOrchestratorSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: evaluationCompleteTopic
  name: 'orchestrator-sub'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M'
  }
}

resource healingEventsTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'healing-events'
  properties: {
    defaultMessageTimeToLive: 'P1D'
  }
}

resource healingEventsHealerSub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: healingEventsTopic
  name: 'healer'
  properties: {
    maxDeliveryCount: 10
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT5M'
  }
}

// API Gateway → Orchestrator command queue
resource orchestratorCommandsQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'orchestrator-commands'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    defaultMessageTimeToLive: 'P1D'
    lockDuration: 'PT5M'
  }
}

// System-status topic (published by services, consumed by API gateway)
resource systemStatusTopic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'system-status'
  properties: {
    defaultMessageTimeToLive: 'PT1H'
  }
}

resource systemStatusApiGatewaySub 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' = {
  parent: systemStatusTopic
  name: 'api-gateway'
  properties: {
    maxDeliveryCount: 5
    deadLetteringOnMessageExpiration: true
    lockDuration: 'PT1M'
  }
}

output namespaceId string = serviceBusNamespace.id
output namespaceName string = serviceBusNamespace.name
output fullyQualifiedNamespace string = '${serviceBusNamespace.name}.servicebus.windows.net'
