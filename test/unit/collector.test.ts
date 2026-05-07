// Mock all AWS SDK clients before importing the collector module
jest.mock('@aws-sdk/client-resource-groups-tagging-api');
jest.mock('@aws-sdk/client-auto-scaling');
jest.mock('@aws-sdk/client-ec2');
jest.mock('@aws-sdk/client-lambda');
jest.mock('@aws-sdk/client-ecs');
jest.mock('@aws-sdk/client-elastic-load-balancing-v2');
jest.mock('@aws-sdk/client-elastic-load-balancing');
jest.mock('@aws-sdk/client-rds');
jest.mock('@aws-sdk/client-dynamodb');
jest.mock('@aws-sdk/client-api-gateway');
jest.mock('@aws-sdk/client-apigatewayv2');
jest.mock('@aws-sdk/client-cloudfront');
jest.mock('@aws-sdk/client-sqs');
jest.mock('@aws-sdk/client-efs');
jest.mock('@aws-sdk/client-cloudwatch');
jest.mock('@aws-sdk/client-s3');
jest.mock('@aws-sdk/client-mediapackage');
jest.mock('@aws-sdk/client-medialive');
jest.mock('@aws-sdk/client-appsync');

import { LambdaClient, GetFunctionCommand } from '@aws-sdk/client-lambda';
import { DynamoDBClient, DescribeTableCommand } from '@aws-sdk/client-dynamodb';
import { RDSClient, DescribeDBClustersCommand } from '@aws-sdk/client-rds';
import { EFSClient, DescribeFileSystemsCommand } from '@aws-sdk/client-efs';
import { EC2Client, DescribeVolumesCommand, DescribeInstancesCommand, DescribeInstanceCreditSpecificationsCommand } from '@aws-sdk/client-ec2';
import { CloudWatchClient, ListMetricsCommand } from '@aws-sdk/client-cloudwatch';
import { router, TaggedResource } from '../../src/collector/index';

// Helper to set up mocked send function for a client
function mockClientSend(ClientClass: any, responses: Record<string, any>) {
  const mockSend = jest.fn().mockImplementation((command: any) => {
    const commandName = command.constructor.name;
    if (responses[commandName]) {
      return Promise.resolve(responses[commandName]);
    }
    return Promise.resolve({});
  });
  (ClientClass as jest.Mock).mockImplementation(() => ({
    send: mockSend,
  }));
  return mockSend;
}

describe('Collector Router', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should return resource unchanged for unrecognized ARN patterns', async () => {
    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:unknown:us-east-1:123456789:something/abc',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result).toBe(resource);
    expect(result.ResourceARN).toBe(resource.ResourceARN);
  });

  it('should return resource unchanged for SNS ARN', async () => {
    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:sns:us-east-1:123456789:my-topic',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result).toBe(resource);
  });

  it('should return resource unchanged for autoscaling group ARN', async () => {
    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:autoscaling:us-east-1:123456789:autoScalingGroup:abc-123:autoScalingGroupName/my-asg',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result).toBe(resource);
  });

  it('should return resource unchanged for NAT gateway ARN', async () => {
    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:ec2:us-east-1:123456789:natgateway/nat-abc123',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result).toBe(resource);
  });

  it('should route Lambda ARN to lambdaDecorator', async () => {
    mockClientSend(LambdaClient, {
      GetFunctionCommand: {
        Configuration: {
          FunctionName: 'my-function',
          Runtime: 'nodejs18.x',
          MemorySize: 128,
        },
      },
    });

    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:lambda:us-east-1:123456789:function:my-function',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result.Configuration).toEqual({
      FunctionName: 'my-function',
      Runtime: 'nodejs18.x',
      MemorySize: 128,
    });
  });

  it('should route DynamoDB ARN to dynamodbDecorator', async () => {
    mockClientSend(DynamoDBClient, {
      DescribeTableCommand: {
        Table: {
          TableName: 'my-table',
          ProvisionedThroughput: {
            ReadCapacityUnits: 5,
            WriteCapacityUnits: 10,
          },
        },
      },
    });

    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:dynamodb:us-east-1:123456789:table/my-table',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result.type).toBe('provisioned');
    expect(result.rcu).toBe(5);
    expect(result.wcu).toBe(10);
  });

  it('should route DynamoDB on-demand table correctly', async () => {
    mockClientSend(DynamoDBClient, {
      DescribeTableCommand: {
        Table: {
          TableName: 'my-ondemand-table',
          BillingModeSummary: { BillingMode: 'PAY_PER_REQUEST' },
          ProvisionedThroughput: {
            ReadCapacityUnits: 0,
            WriteCapacityUnits: 0,
          },
        },
      },
    });

    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:dynamodb:us-east-1:123456789:table/my-ondemand-table',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result.type).toBe('ondemand');
  });

  it('should route RDS cluster ARN to auroraDecorator', async () => {
    mockClientSend(RDSClient, {
      DescribeDBClustersCommand: {
        DBClusters: [
          {
            Engine: 'aurora-mysql',
            EngineMode: 'provisioned',
            MultiAZ: true,
            Endpoint: 'my-cluster.cluster-abc.us-east-1.rds.amazonaws.com',
            ReaderEndpoint: 'my-cluster.cluster-ro-abc.us-east-1.rds.amazonaws.com',
            EngineVersion: '8.0.mysql_aurora.3.04.0',
            DBClusterMembers: [],
            ReadReplicaIdentifiers: [],
            StorageType: 'aurora',
            PerformanceInsightsEnabled: true,
          },
        ],
      },
    });

    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:rds:us-east-1:123456789:cluster:my-cluster',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result.Engine).toBe('aurora-mysql');
    expect(result.MultiAZ).toBe(true);
    expect(result.PerformanceInsightsEnabled).toBe(true);
  });

  it('should route EFS ARN to efsDecorator', async () => {
    mockClientSend(EFSClient, {
      DescribeFileSystemsCommand: {
        FileSystems: [
          {
            FileSystemId: 'fs-abc123',
            ThroughputMode: 'bursting',
          },
        ],
      },
    });

    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:elasticfilesystem:us-east-1:123456789:file-system/fs-abc123',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result.ThroughputMode).toBe('bursting');
  });

  it('should route EC2 instance ARN to ec2Decorator', async () => {
    mockClientSend(EC2Client, {
      DescribeVolumesCommand: {
        Volumes: [{ VolumeId: 'vol-abc123', Size: 100 }],
        NextToken: undefined,
      },
      DescribeInstancesCommand: {
        Reservations: [
          {
            Instances: [
              {
                InstanceId: 'i-abc123',
                InstanceType: 'm5.large',
              },
            ],
          },
        ],
      },
    });
    mockClientSend(CloudWatchClient, {
      ListMetricsCommand: {
        Metrics: [],
      },
    });

    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:ec2:us-east-1:123456789:instance/i-abc123',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    const result = await router(resource, 'us-east-1');
    expect(result.Instance).toEqual({
      InstanceId: 'i-abc123',
      InstanceType: 'm5.large',
    });
    expect(result.Volumes).toEqual([{ VolumeId: 'vol-abc123', Size: 100 }]);
    expect(result.CWAgent).toBe('False');
  });

  it('should propagate errors from decorators (not swallow them)', async () => {
    (LambdaClient as jest.Mock).mockImplementation(() => ({
      send: jest.fn().mockRejectedValue(new Error('Throttled')),
    }));

    const resource: TaggedResource = {
      ResourceARN: 'arn:aws:lambda:us-east-1:123456789:function:my-function',
      Tags: [{ Key: 'env', Value: 'prod' }],
    };
    await expect(router(resource, 'us-east-1')).rejects.toThrow('Throttled');
  });
});
