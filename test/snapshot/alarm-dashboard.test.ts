import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { AlarmDashboardStack } from '../../src/stacks/alarm-dashboard-stack';

const testConfig = {
  BaseName: 'TestAlarmApp',
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
  AlarmDashboard: {
    enabled: true,
    organizationId: 'o-testorg12345',
    alarmViewListSize: 100,
  },
  MetricDashboards: { enabled: true },
};

describe('AlarmDashboardStack', () => {
  let template: ReturnType<typeof Template.fromStack>;

  beforeAll(() => {
    const app = new App();
    const stack = new AlarmDashboardStack(app, 'TestAlarmDashboardStack', {
      config: testConfig as any,
    });
    template = Template.fromStack(stack);
  });

  it('should create a CloudWatch Dashboard', () => {
    template.resourceCountIs('AWS::CloudWatch::Dashboard', 1);
  });

  it('should create 4 Lambda functions with Python 3.12', () => {
    const resources = template.toJSON().Resources;
    const lambdas = Object.values(resources).filter((r: any) => r.Type === 'AWS::Lambda::Function') as any[];
    expect(lambdas.length).toBe(4);
    lambdas.forEach((lambda) => {
      expect(lambda.Properties.Runtime).toBe('python3.12');
    });
  });

  it('should create a DynamoDB table with TTL', () => {
    template.resourceCountIs('AWS::DynamoDB::Table', 1);
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      TimeToLiveSpecification: {
        AttributeName: 'ttl',
        Enabled: true,
      },
    });
  });

  it('should create an EventBus', () => {
    template.resourceCountIs('AWS::Events::EventBus', 1);
  });

  it('should create SSM Parameter', () => {
    template.hasResourceProperties('AWS::SSM::Parameter', {
      Name: 'CloudWatchAlarmWidgetConfigCDK',
      Type: 'String',
    });
  });
});
