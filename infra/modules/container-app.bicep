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

@description('Minimum replicas (0 allows scale-to-zero, 1 keeps always-on)')
param minReplicas int = 0

@description('Environment variables for the container')
param env array = []

@description('Key Vault URI (e.g. https://kv-xxxx.vault.azure.net/) for secret references')
param keyVaultUri string = ''

@description('Key Vault-backed secrets to mount into the container app')
param secrets array = []

@description('Service Bus namespace (fully qualified) for KEDA scaling — leave empty to disable')
param serviceBusNamespace string = ''

@description('Service Bus queue name for KEDA queue-based scaling')
param serviceBusQueueName string = ''

@description('Service Bus topic name for KEDA topic-based scaling')
param serviceBusTopicName string = ''

@description('Service Bus subscription name for KEDA topic-based scaling')
param serviceBusSubscriptionName string = ''

@description('Managed Identity resource ID used for KEDA Service Bus authentication')
param scaleIdentityId string = ''

@description('Messages per replica for KEDA scaling')
param kedaMessageCount int = 20

@description('Use a placeholder public image instead of the ACR image. Set to true only on the very first azd provision before any images have been pushed to ACR. Defaults to false so that steady-state re-provisions always use the real ACR image.')
param useDefaultImage bool = false

var hasQueueScale = !empty(serviceBusNamespace) && !empty(serviceBusQueueName)
var hasTopicScale = !empty(serviceBusNamespace) && !empty(serviceBusTopicName) && !empty(serviceBusSubscriptionName)

var queueScaleRule = {
  name: 'sb-queue-scale'
  custom: {
    type: 'azure-servicebus'
    identity: scaleIdentityId
    metadata: {
      namespace: serviceBusNamespace
      queueName: serviceBusQueueName
      messageCount: string(kedaMessageCount)
      activationMessageCount: '1'
    }
  }
}

var topicScaleRule = {
  name: 'sb-topic-scale'
  custom: {
    type: 'azure-servicebus'
    identity: scaleIdentityId
    metadata: {
      namespace: serviceBusNamespace
      topicName: serviceBusTopicName
      subscriptionName: serviceBusSubscriptionName
      messageCount: string(kedaMessageCount)
      activationMessageCount: '1'
    }
  }
}

var kedaScaleRules = hasQueueScale ? [queueScaleRule] : hasTopicScale ? [topicScaleRule] : []

var acrImage = '${containerRegistryLoginServer}/selflearning-${serviceName}:latest'
var defaultImage = 'mcr.microsoft.com/k8se/quickstart:latest'
var containerImage = useDefaultImage ? defaultImage : acrImage
// The quickstart placeholder listens on port 80; real services use the caller-supplied targetPort.
var effectiveTargetPort = useDefaultImage ? 80 : targetPort

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
      secrets: [
        for secret in secrets: {
          name: secret.name
          keyVaultUrl: '${keyVaultUri}secrets/${secret.kvSecretName}'
          identity: identityId
        }
      ]
      ingress: {
        external: external
        targetPort: effectiveTargetPort
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
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: env
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 10
        rules: kedaScaleRules
      }
    }
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output name string = containerApp.name
