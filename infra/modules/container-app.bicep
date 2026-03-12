@description('Location for the resource')
param location string

@description('Tags for all resources')
param tags object

@description('Name of the service')
param serviceName string

@description('Container Apps Environment ID')
param containerAppsEnvironmentId string

@description('Container Registry login server')
param containerRegistryLoginServer string

@description('Managed Identity resource ID')
param identityId string

@description('Managed Identity client ID')
param identityClientId string

@description('Whether to expose external ingress')
param external bool = false

@description('Target port for the container')
param targetPort int = 8000

@description('Environment variables for the container')
param env array = []

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${serviceName}'
  location: location
  tags: union(tags, { 'azd-service-name': serviceName })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: external
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: containerRegistryLoginServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: serviceName
          image: '${containerRegistryLoginServer}/selflearning-${serviceName}:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: env
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 10
      }
    }
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output name string = containerApp.name
