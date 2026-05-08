import * as fs from 'fs';
import * as path from 'path';
import { ResourceGroupsTaggingAPIClient, GetResourcesCommand } from '@aws-sdk/client-resource-groups-tagging-api';
import { AutoScalingClient, DescribeAutoScalingGroupsCommand } from '@aws-sdk/client-auto-scaling';
import {
  EC2Client,
  DescribeVolumesCommand,
  DescribeInstancesCommand,
  DescribeInstanceCreditSpecificationsCommand,
  DescribeTransitGatewayAttachmentsCommand,
} from '@aws-sdk/client-ec2';
import { LambdaClient, GetFunctionCommand } from '@aws-sdk/client-lambda';
import { ECSClient, DescribeClustersCommand, ListServicesCommand, DescribeServicesCommand } from '@aws-sdk/client-ecs';
import {
  ElasticLoadBalancingV2Client,
  DescribeLoadBalancersCommand as DescribeLoadBalancersV2Command,
  DescribeTargetGroupsCommand,
  DescribeTargetHealthCommand,
} from '@aws-sdk/client-elastic-load-balancing-v2';
import {
  ElasticLoadBalancingClient,
  DescribeLoadBalancersCommand as DescribeLoadBalancersV1Command,
} from '@aws-sdk/client-elastic-load-balancing';
import { RDSClient, DescribeDBClustersCommand } from '@aws-sdk/client-rds';
import { DynamoDBClient, DescribeTableCommand } from '@aws-sdk/client-dynamodb';
import { APIGatewayClient, GetRestApiCommand, GetStagesCommand } from '@aws-sdk/client-api-gateway';
import { ApiGatewayV2Client, GetApiCommand } from '@aws-sdk/client-apigatewayv2';
import { CloudFrontClient, GetDistributionCommand } from '@aws-sdk/client-cloudfront';
import { SQSClient, GetQueueUrlCommand, GetQueueAttributesCommand } from '@aws-sdk/client-sqs';
import { EFSClient, DescribeFileSystemsCommand } from '@aws-sdk/client-efs';
import { CloudWatchClient, ListMetricsCommand } from '@aws-sdk/client-cloudwatch';
import { S3Client, GetBucketEncryptionCommand, GetBucketLocationCommand } from '@aws-sdk/client-s3';
import {
  MediaPackageClient,
  ListChannelsCommand,
  DescribeChannelCommand,
  ListOriginEndpointsCommand,
} from '@aws-sdk/client-mediapackage';
import {
  MediaLiveClient,
  ListChannelsCommand as MediaLiveListChannelsCommand,
  DescribeChannelCommand as MediaLiveDescribeChannelCommand,
} from '@aws-sdk/client-medialive';
import { AppSyncClient, GetGraphqlApiCommand } from '@aws-sdk/client-appsync';
import { loadConfig } from '../../config/config.schema';

export interface ResourceTag {
  Key: string;
  Value: string;
}

export interface TaggedResource {
  ResourceARN: string;
  Tags: ResourceTag[];
  [key: string]: any;
}

function getClientConfig(region: string) {
  return {
    region,
    maxAttempts: 10,
  };
}

async function getResources(tagName: string, tagValues: string[], region: string): Promise<TaggedResource[]> {
  const client = new ResourceGroupsTaggingAPIClient(getClientConfig(region));
  const resources: TaggedResource[] = [];

  const batchSize = 5;
  for (let i = 0; i < tagValues.length; i += batchSize) {
    const batch = tagValues.slice(i, i + batchSize);
    let paginationToken: string | undefined;

    do {
      const command = new GetResourcesCommand({
        TagFilters: [{ Key: tagName, Values: batch }],
        ResourcesPerPage: 40,
        PaginationToken: paginationToken,
      });
      const response = await client.send(command);
      if (response.ResourceTagMappingList) {
        for (const r of response.ResourceTagMappingList) {
          resources.push({
            ResourceARN: r.ResourceARN || '',
            Tags: (r.Tags || []).map((t) => ({ Key: t.Key || '', Value: t.Value || '' })),
          });
        }
      }
      paginationToken = response.PaginationToken || undefined;
    } while (paginationToken);
  }

  // Also get autoscaling groups (not supported by tagging API)
  const asgResources = await getAutoScalingGroups(tagName, tagValues, region);
  resources.push(...asgResources);

  return resources;
}

async function getAutoScalingGroups(tagName: string, tagValues: string[], region: string): Promise<TaggedResource[]> {
  const client = new AutoScalingClient(getClientConfig(region));
  const resources: TaggedResource[] = [];

  const batchSize = 5;
  for (let i = 0; i < tagValues.length; i += batchSize) {
    const batch = tagValues.slice(i, i + batchSize);
    let nextToken: string | undefined;

    do {
      const command = new DescribeAutoScalingGroupsCommand({
        Filters: [{ Name: `tag:${tagName}`, Values: batch }],
        MaxRecords: 10,
        NextToken: nextToken,
      });
      const response = await client.send(command);
      if (response.AutoScalingGroups) {
        for (const asg of response.AutoScalingGroups) {
          const resource: TaggedResource = {
            ...asg,
            ResourceARN: asg.AutoScalingGroupARN || '',
            Tags: (asg.Tags || []).map((t) => ({ Key: t.Key || '', Value: t.Value || '' })),
          } as any;
          resources.push(resource);
        }
      }
      nextToken = response.NextToken;
    } while (nextToken);
  }

  return resources;
}

export async function router(resource: TaggedResource, region: string): Promise<TaggedResource> {
  const arn = resource.ResourceARN;

  if (arn.includes(':apigateway:') && arn.includes('/restapis/') && !arn.includes('stages')) {
    return apigw1Decorator(resource, region);
  } else if (arn.includes(':apigateway:') && arn.includes('/apis/') && !arn.includes('stages')) {
    return apigw2Decorator(resource, region);
  } else if (arn.includes(':appsync:')) {
    return appsyncDecorator(resource, region);
  } else if (arn.includes(':rds:') && arn.includes(':cluster:')) {
    return auroraDecorator(resource, region);
  } else if (arn.includes(':autoscaling:') && arn.includes(':autoScalingGroup:')) {
    return resource; // Already decorated from ASG retrieval
  } else if (arn.includes(':capacity-reservation/')) {
    return resource;
  } else if (arn.includes(':dynamodb:') && arn.includes(':table/')) {
    return dynamodbDecorator(resource, region);
  } else if (arn.includes(':ec2:') && arn.includes(':instance/')) {
    return ec2Decorator(resource, region);
  } else if (arn.includes('lambda') && arn.includes('function')) {
    return lambdaDecorator(resource, region);
  } else if (
    arn.includes('elasticloadbalancing') &&
    !arn.includes('/net/') &&
    !arn.includes('/app/') &&
    !arn.includes(':targetgroup/')
  ) {
    return elb1Decorator(resource, region);
  } else if (
    arn.includes('elasticloadbalancing') &&
    (arn.includes('/net/') || arn.includes('/app/')) &&
    !arn.includes(':targetgroup/') &&
    !arn.includes(':listener/')
  ) {
    return elb2Decorator(resource, region);
  } else if (arn.includes(':ecs:') && arn.includes(':cluster/')) {
    return ecsDecorator(resource, region);
  } else if (arn.includes(':natgateway/') && arn.includes(':ec2:')) {
    return resource;
  } else if (arn.includes(':transit-gateway/') && arn.includes(':ec2:')) {
    return tgwDecorator(resource, region);
  } else if (arn.includes(':sqs:')) {
    return sqsDecorator(resource, region);
  } else if (arn.includes('arn:aws:s3:')) {
    return s3Decorator(resource, region);
  } else if (arn.includes(':sns:')) {
    return resource;
  } else if (arn.includes(':cloudfront:') && arn.includes(':distribution/')) {
    return cloudfrontDecorator(resource, region);
  } else if (arn.includes(':mediapackage:') && arn.includes(':channels/')) {
    return mediapackageDecorator(resource, region);
  } else if (arn.includes(':medialive:') && arn.includes(':channel:')) {
    return medialiveDecorator(resource, region);
  } else if (arn.includes(':elasticfilesystem:')) {
    return efsDecorator(resource, region);
  }

  return resource;
}

async function apigw1Decorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is API Gateway 1 ${resource.ResourceARN}`);
  const apiid = resource.ResourceARN.split('/').pop()!;
  const client = new APIGatewayClient(getClientConfig(region));

  const response = await client.send(new GetRestApiCommand({ restApiId: apiid }));
  const stages = await client.send(new GetStagesCommand({ restApiId: apiid }));

  resource['name'] = response.name || '';
  resource['endpointConfiguration'] = response.endpointConfiguration?.types?.[0] || '';
  resource['disableExecuteApiEndpoint'] = response.disableExecuteApiEndpoint || false;
  resource['stages'] = stages.item || [];
  return resource;
}

async function apigw2Decorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is API Gateway 2 ${resource.ResourceARN}`);
  const apiid = resource.ResourceARN.split('/').pop()!;
  const client = new ApiGatewayV2Client(getClientConfig(region));

  const response = await client.send(new GetApiCommand({ ApiId: apiid }));
  resource['name'] = response.Name || '';
  resource['apiid'] = response.ApiId || '';
  resource['type'] = response.ProtocolType || '';
  resource['disableExecuteApiEndpoint'] = response.DisableExecuteApiEndpoint || false;
  resource['endpoint'] = response.ApiEndpoint || '';
  return resource;
}

async function appsyncDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is AppSync ${resource.ResourceARN}`);
  const apiid = resource.ResourceARN.split('/').pop()!;
  const client = new AppSyncClient(getClientConfig(region));

  const response = await client.send(new GetGraphqlApiCommand({ apiId: apiid }));
  resource['name'] = response.graphqlApi?.name || '';
  resource['apiId'] = response.graphqlApi?.apiId || '';
  resource['xrayEnabled'] = response.graphqlApi?.xrayEnabled || false;
  resource['realtimeUri'] = response.graphqlApi?.uris?.['REALTIME'] || '';
  resource['graphqlUri'] = response.graphqlApi?.uris?.['GRAPHQL'] || '';
  return resource;
}

async function auroraDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is Aurora ${resource.ResourceARN}`);
  const clusterid = resource.ResourceARN.split(':').pop()!;
  const client = new RDSClient(getClientConfig(region));

  try {
    const response = await client.send(new DescribeDBClustersCommand({ DBClusterIdentifier: clusterid }));
    const cluster = response.DBClusters?.[0];
    if (cluster) {
      resource['MultiAZ'] = cluster.MultiAZ;
      resource['Engine'] = cluster.Engine;
      resource['EngineMode'] = cluster.EngineMode;
      resource['DBClusterMembers'] = cluster.DBClusterMembers;
      resource['Endpoint'] = cluster.Endpoint;
      resource['ReaderEndpoint'] = cluster.ReaderEndpoint;
      resource['EngineVersion'] = cluster.EngineVersion;
      resource['ReadReplicaIdentifiers'] = cluster.ReadReplicaIdentifiers;
      resource['StorageType'] = cluster.StorageType;
      resource['PerformanceInsightsEnabled'] = cluster.PerformanceInsightsEnabled;
    }
  } catch (e) {
    console.log('Just aurora-resource');
  }
  return resource;
}

async function dynamodbDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is DynamoDB ${resource.ResourceARN}`);
  const tablename = resource.ResourceARN.split('/').pop()!;
  const client = new DynamoDBClient(getClientConfig(region));

  const response = await client.send(new DescribeTableCommand({ TableName: tablename }));
  const table = response.Table;
  if (table) {
    const type = table.BillingModeSummary ? 'ondemand' : 'provisioned';
    resource['type'] = type;
    resource['wcu'] = table.ProvisionedThroughput?.WriteCapacityUnits || 0;
    resource['rcu'] = table.ProvisionedThroughput?.ReadCapacityUnits || 0;
  }
  return resource;
}

async function ec2Decorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is EC2 ${resource.ResourceARN}`);
  const instanceid = resource.ResourceARN.split('/').pop()!;
  const ec2 = new EC2Client(getClientConfig(region));

  // Get volumes
  const volumes: any[] = [];
  let nextToken: string | undefined;
  do {
    const volResponse = await ec2.send(
      new DescribeVolumesCommand({
        Filters: [{ Name: 'attachment.instance-id', Values: [instanceid] }],
        MaxResults: 100,
        NextToken: nextToken,
      }),
    );
    if (volResponse.Volumes) {
      volumes.push(...volResponse.Volumes);
    }
    nextToken = volResponse.NextToken;
  } while (nextToken);
  resource['Volumes'] = volumes;

  // Get instance details
  const instResponse = await ec2.send(
    new DescribeInstancesCommand({
      Filters: [{ Name: 'instance-id', Values: [instanceid] }],
    }),
  );
  resource['Instance'] = instResponse.Reservations?.[0]?.Instances?.[0] || {};
  const instanceType = resource['Instance'].InstanceType || '';

  // Check for burstable instance types
  if (instanceType.includes('t2') || instanceType.includes('t3') || instanceType.includes('t4')) {
    const creditResponse = await ec2.send(
      new DescribeInstanceCreditSpecificationsCommand({
        InstanceIds: [instanceid],
      }),
    );
    resource['CPUCreditSpecs'] = creditResponse.InstanceCreditSpecifications?.[0] || {};
  }

  // Check for CWAgent metrics
  const cw = new CloudWatchClient(getClientConfig(region));
  const metricsResponse = await cw.send(
    new ListMetricsCommand({
      MetricName: 'mem_used_percent',
      Namespace: 'CWAgent',
      Dimensions: [{ Name: 'InstanceId', Value: instanceid }],
    }),
  );
  resource['CWAgent'] = metricsResponse.Metrics && metricsResponse.Metrics.length > 0 ? 'True' : 'False';

  return resource;
}

async function lambdaDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is Lambda ${resource.ResourceARN}`);
  const functionname = resource.ResourceARN.split(':').pop()!;
  const client = new LambdaClient(getClientConfig(region));

  const response = await client.send(new GetFunctionCommand({ FunctionName: functionname }));
  resource['Configuration'] = response.Configuration || {};
  return resource;
}

async function elb1Decorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is ELBv1 ${resource.ResourceARN}`);
  const elbname = resource.ResourceARN.split('/').pop()!;
  const client = new ElasticLoadBalancingClient(getClientConfig(region));

  const response = await client.send(
    new DescribeLoadBalancersV1Command({
      LoadBalancerNames: [elbname],
    }),
  );
  resource['Extras'] = response.LoadBalancerDescriptions?.[0] || {};
  return resource;
}

async function elb2Decorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is ELBv2 ${resource.ResourceARN}`);
  const client = new ElasticLoadBalancingV2Client(getClientConfig(region));

  const response = await client.send(
    new DescribeLoadBalancersV2Command({
      LoadBalancerArns: [resource.ResourceARN],
    }),
  );
  resource['Extras'] = response.LoadBalancers?.[0] || {};

  const tgResponse = await client.send(
    new DescribeTargetGroupsCommand({
      LoadBalancerArn: resource.ResourceARN,
    }),
  );
  resource['TargetGroups'] = tgResponse.TargetGroups || [];
  return resource;
}

async function ecsDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is ECS ${resource.ResourceARN}`);
  const ecsClient = new ECSClient(getClientConfig(region));

  const clusterResponse = await ecsClient.send(
    new DescribeClustersCommand({
      clusters: [resource.ResourceARN],
    }),
  );
  resource['cluster'] = clusterResponse.clusters?.[0] || {};

  const listResponse = await ecsClient.send(
    new ListServicesCommand({
      cluster: resource.ResourceARN,
    }),
  );

  if (listResponse.serviceArns && listResponse.serviceArns.length > 0) {
    const svcResponse = await ecsClient.send(
      new DescribeServicesCommand({
        cluster: resource.ResourceARN,
        services: listResponse.serviceArns,
      }),
    );

    const services = (svcResponse.services || []).map((service: any) => {
      delete service.events;
      return service;
    });

    const elbClient = new ElasticLoadBalancingV2Client(getClientConfig(region));
    for (const service of services) {
      const targetGroups: string[] = [];
      const instances: string[] = [];

      if (service.launchType === 'EC2') {
        for (const lb of service.loadBalancers || []) {
          if (lb.targetGroupArn) targetGroups.push(lb.targetGroupArn);
        }
      }

      for (const tgArn of targetGroups) {
        const healthResponse = await elbClient.send(
          new DescribeTargetHealthCommand({
            TargetGroupArn: tgArn,
          }),
        );
        for (const desc of healthResponse.TargetHealthDescriptions || []) {
          if (desc.Target?.Id) instances.push(desc.Target.Id);
        }
      }

      service.instances = instances;
    }
    resource['services'] = services;
  } else {
    resource['services'] = [];
  }

  return resource;
}

async function tgwDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is TGW ${resource.ResourceARN}`);
  const tgwid = resource.ResourceARN.split('/').pop()!;
  const client = new EC2Client(getClientConfig(region));

  const response = await client.send(
    new DescribeTransitGatewayAttachmentsCommand({
      Filters: [{ Name: 'transit-gateway-id', Values: [tgwid] }],
    }),
  );
  resource['attachments'] = response.TransitGatewayAttachments || [];
  return resource;
}

async function sqsDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is SQS ${resource.ResourceARN}`);
  const queueName = resource.ResourceARN.split(':').pop()!;
  const client = new SQSClient(getClientConfig(region));

  const urlResponse = await client.send(new GetQueueUrlCommand({ QueueName: queueName }));
  const attrResponse = await client.send(
    new GetQueueAttributesCommand({
      AttributeNames: ['All'],
      QueueUrl: urlResponse.QueueUrl!,
    }),
  );
  resource['Attributes'] = attrResponse.Attributes || {};
  return resource;
}

async function s3Decorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  const bucketName = resource.ResourceARN.split(':').pop()!;
  console.log(`This resource ${bucketName} is S3 bucket`);
  resource['BucketName'] = bucketName;
  const client = new S3Client(getClientConfig(region));

  try {
    const encResponse = await client.send(new GetBucketEncryptionCommand({ Bucket: bucketName }));
    const rule = encResponse.ServerSideEncryptionConfiguration?.Rules?.[0];
    const encType = rule?.ApplyServerSideEncryptionByDefault?.SSEAlgorithm === 'aws:kms' ? 'SSE-KMS' : 'SSE-S3';
    resource['Encryption'] = {
      Type: encType,
      BucketKeyEnabled: rule?.BucketKeyEnabled || false,
    };
  } catch {
    resource['Encryption'] = false;
  }

  const locResponse = await client.send(new GetBucketLocationCommand({ Bucket: bucketName }));
  resource['Region'] = locResponse.LocationConstraint || 'us-east-1';
  return resource;
}

async function cloudfrontDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is CloudFront distribution`);
  const distId = resource.ResourceARN.split('/').pop()!;
  const client = new CloudFrontClient(getClientConfig(region));

  const response = await client.send(new GetDistributionCommand({ Id: distId }));
  resource['Id'] = response.Distribution?.Id || '';
  resource['ARN'] = response.Distribution?.ARN || '';
  resource['DomainName'] = response.Distribution?.DomainName || '';
  resource['Aliases'] = response.Distribution?.DistributionConfig?.Aliases || {};
  resource['Origins'] = response.Distribution?.DistributionConfig?.Origins || {};
  return resource;
}

async function mediapackageDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is MediaPackage channel`);
  const client = new MediaPackageClient(getClientConfig(region));

  const response = await client.send(new ListChannelsCommand({ MaxResults: 40 }));
  for (const channel of response.Channels || []) {
    if (channel.Arn === resource.ResourceARN) {
      resource['Id'] = channel.Id || '';
      resource['ARN'] = channel.Arn || '';

      const detail = await client.send(new DescribeChannelCommand({ Id: channel.Id! }));
      resource['IngestEndpoint'] = detail.HlsIngest?.IngestEndpoints || [];

      const origins = await client.send(new ListOriginEndpointsCommand({ ChannelId: channel.Id! }));
      resource['OriginEndpoint'] = origins.OriginEndpoints || [];
      break;
    }
  }
  return resource;
}

async function medialiveDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is MediaLive channel`);
  const client = new MediaLiveClient(getClientConfig(region));

  const response = await client.send(new MediaLiveListChannelsCommand({ MaxResults: 40 }));
  for (const channel of response.Channels || []) {
    if (channel.Arn === resource.ResourceARN) {
      resource['ARN'] = channel.Arn || '';
      resource['id'] = channel.Id || '';

      const detail = await client.send(new MediaLiveDescribeChannelCommand({ ChannelId: channel.Id! }));
      resource['Pipeline'] = detail.PipelineDetails || [];
      break;
    }
  }
  return resource;
}

async function efsDecorator(resource: TaggedResource, region: string): Promise<TaggedResource> {
  console.log(`This resource is EFS ${resource.ResourceARN}`);
  const fsId = resource.ResourceARN.split('/').pop()!;
  const client = new EFSClient(getClientConfig(region));

  const response = await client.send(new DescribeFileSystemsCommand({ FileSystemId: fsId }));
  resource['ThroughputMode'] = response.FileSystems?.[0]?.ThroughputMode || '';
  return resource;
}

async function collectCustomNamespaces(region: string): Promise<string[]> {
  const client = new CloudWatchClient(getClientConfig(region));
  const namespaces: string[] = [];
  let nextToken: string | undefined;

  do {
    const response = await client.send(new ListMetricsCommand({ NextToken: nextToken }));
    for (const metric of response.Metrics || []) {
      const ns = metric.Namespace || '';
      if (!ns.startsWith('AWS/') && !ns.startsWith('CWAgent') && !namespaces.includes(ns)) {
        namespaces.push(ns);
      }
    }
    nextToken = response.NextToken;
  } while (nextToken);

  return namespaces;
}

async function handler() {
  const config = loadConfig();
  const tagName = config.TagKey;
  const tagValues = config.TagValues;
  const regions = [...config.Regions];
  const outputFile = config.ResourceFile;
  const customNamespaceFile = config.CustomNamespaceFile;

  if (!regions.includes('us-east-1')) {
    regions.push('us-east-1');
    console.log('Added us-east-1 region for global services');
  }

  const decoratedResources: TaggedResource[] = [];
  const regionNamespaces: { RegionNamespaces: Array<{ Region: string; Namespaces: string[] }> } = {
    RegionNamespaces: [],
  };
  const failures: Array<{ arn: string; error: unknown }> = [];

  for (const region of regions) {
    console.log(`Processing region: ${region}`);
    const resources = await getResources(tagName, tagValues, region);
    const namespaces = await collectCustomNamespaces(region);
    regionNamespaces.RegionNamespaces.push({ Region: region, Namespaces: namespaces });

    for (const resource of resources) {
      try {
        const decorated = await router(resource, region);
        decoratedResources.push(decorated);
      } catch (e) {
        console.error(`Error decorating resource ${resource.ResourceARN}:`, e);
        failures.push({ arn: resource.ResourceARN, error: e });
      }
    }
  }

  if (failures.length > 0) {
    console.error(`\n--- Decoration Failures Summary ---`);
    console.error(`${failures.length} resource(s) failed decoration:`);
    for (const f of failures) {
      console.error(`  - ${f.arn}`);
    }
    console.error(`Aborting: failed resources would produce incomplete data that breaks synthesis.`);
    process.exit(1);
  }

  const outputPath = path.resolve(__dirname, '../../', outputFile);
  const namespacePath = path.resolve(__dirname, '../../', customNamespaceFile);

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(decoratedResources, null, 4));
  console.log(`Wrote ${decoratedResources.length} resources to ${outputPath}`);

  fs.mkdirSync(path.dirname(namespacePath), { recursive: true });
  fs.writeFileSync(namespacePath, JSON.stringify(regionNamespaces, null, 4));
  console.log(`Wrote custom namespaces to ${namespacePath}`);
}

/* istanbul ignore next */
if (require.main === module) {
  handler().catch((err) => {
    console.error('Resource collection failed:', err);
    process.exit(1);
  });
}
