import { App, Stack } from 'aws-cdk-lib';
import { GraphFactory } from '../../src/constructs/graph-factory';

describe('GraphFactory', () => {
  const sampleResources = [
    {
      ResourceARN: 'arn:aws:lambda:us-east-1:123456789012:function:MyTestFunction',
      Tags: [
        { Key: 'environment', Value: 'production' },
        { Key: 'Name', Value: 'MyTestFunction' },
      ],
      Configuration: {
        FunctionName: 'MyTestFunction',
        MemorySize: 256,
        Runtime: 'nodejs18.x',
        Timeout: 30,
      },
    },
    {
      ResourceARN: 'arn:aws:dynamodb:us-east-1:123456789012:table/MyTestTable',
      Tags: [{ Key: 'environment', Value: 'production' }],
      type: 'provisioned',
      wcu: 5,
      rcu: 5,
    },
    {
      ResourceARN: 'arn:aws:sqs:us-east-1:123456789012:MyTestQueue',
      Tags: [{ Key: 'environment', Value: 'production' }],
      Attributes: {
        QueueArn: 'arn:aws:sqs:us-east-1:123456789012:MyTestQueue',
        VisibilityTimeout: '30',
      },
    },
  ];

  const config = {
    BaseName: 'TestApp',
    ResourceFile: './resources.json',
    TagKey: 'environment',
    TagValues: ['production'],
    Regions: ['us-east-1'],
    GroupingTagKey: '',
    CustomEC2TagKeys: [],
    CustomNamespaceFile: './custom_namespaces.json',
    Compact: false,
    CompactMaxResourcesPerWidget: 10,
    AlarmTopic: '',
    AlarmDashboard: { enabled: false, organizationId: '', alarmViewListSize: 100 },
    MetricDashboards: { enabled: true },
  };

  it('should instantiate GraphFactory and create widgets', () => {
    const app = new App();
    const stack = new Stack(app, 'TestStack');
    const factory = new GraphFactory(stack, 'TestGraphFactory', sampleResources, config);
    const widgets = factory.getWidgets();
    expect(widgets.length).toBeGreaterThan(0);
  });

  it('should sort Lambda ARNs into the lambda service key', () => {
    const app = new App();
    const stack = new Stack(app, 'TestStack-Lambda');
    const lambdaResources = [
      {
        ResourceARN: 'arn:aws:lambda:us-east-1:123456789012:function:FuncA',
        Tags: [{ Key: 'environment', Value: 'production' }],
        Configuration: { FunctionName: 'FuncA', MemorySize: 128, Runtime: 'nodejs18.x', Timeout: 10 },
      },
    ];
    const factory = new GraphFactory(stack, 'TestGraphFactory', lambdaResources, config);
    // The factory should have created widgets for the lambda resource
    expect(factory.getWidgets().length).toBeGreaterThan(0);
    // Check that serviceArray has the lambda key
    expect(factory.serviceArray['us-east-1']['lambda']).toBeDefined();
    expect(factory.serviceArray['us-east-1']['lambda'].length).toBe(1);
  });

  it('should sort DynamoDB ARNs into the dynamodb service key', () => {
    const app = new App();
    const stack = new Stack(app, 'TestStack-DDB');
    const ddbResources = [
      {
        ResourceARN: 'arn:aws:dynamodb:us-east-1:123456789012:table/TableA',
        Tags: [{ Key: 'environment', Value: 'production' }],
        type: 'on-demand',
        wcu: 0,
        rcu: 0,
      },
    ];
    const factory = new GraphFactory(stack, 'TestGraphFactory', ddbResources, config);
    expect(factory.serviceArray['us-east-1']['dynamodb']).toBeDefined();
    expect(factory.serviceArray['us-east-1']['dynamodb'].length).toBe(1);
  });

  it('should sort SQS ARNs into the sqs service key', () => {
    const app = new App();
    const stack = new Stack(app, 'TestStack-SQS');
    const sqsResources = [
      {
        ResourceARN: 'arn:aws:sqs:us-east-1:123456789012:QueueA',
        Tags: [{ Key: 'environment', Value: 'production' }],
        Attributes: { QueueArn: 'arn:aws:sqs:us-east-1:123456789012:QueueA' },
      },
    ];
    const factory = new GraphFactory(stack, 'TestGraphFactory', sqsResources, config);
    expect(factory.serviceArray['us-east-1']['sqs']).toBeDefined();
    expect(factory.serviceArray['us-east-1']['sqs'].length).toBe(1);
  });

  it('should sort EC2 instance ARNs into the ec2instances service key', () => {
    const app = new App();
    const stack = new Stack(app, 'TestStack-EC2');
    const ec2Resources = [
      {
        ResourceARN: 'arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0',
        Tags: [
          { Key: 'environment', Value: 'production' },
          { Key: 'Name', Value: 'TestInstance' },
        ],
        Instance: {
          InstanceId: 'i-1234567890abcdef0',
          InstanceType: 't3.micro',
          Placement: { AvailabilityZone: 'us-east-1a' },
          CpuOptions: { CoreCount: 1, ThreadsPerCore: 2 },
        },
        Volumes: [],
        CPUCreditSpecs: { CpuCredits: 'unlimited' },
      },
    ];
    const factory = new GraphFactory(stack, 'TestGraphFactory', ec2Resources, config);
    expect(factory.serviceArray['us-east-1']['ec2instances']).toBeDefined();
    expect(factory.serviceArray['us-east-1']['ec2instances'].length).toBe(1);
  });

  it('should produce alarm sets from resources with alarms', () => {
    const app = new App();
    const stack = new Stack(app, 'TestStack-Alarms');
    // Lambda and DynamoDB both produce alarms
    const factory = new GraphFactory(stack, 'TestGraphFactory', sampleResources, config);
    expect(factory.alarmSet.length).toBeGreaterThan(0);
  });
});
