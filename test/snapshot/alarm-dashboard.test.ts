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

describe('AlarmDashboardStack Snapshot', () => {
  it('should match the snapshot', () => {
    const app = new App();
    const stack = new AlarmDashboardStack(app, 'TestAlarmDashboardStack', { config: testConfig as any });
    const template = Template.fromStack(stack);
    expect(template.toJSON()).toMatchSnapshot();
  });

  it('should create a CloudWatch Dashboard', () => {
    const app = new App();
    const stack = new AlarmDashboardStack(app, 'TestAlarmDashboardStack2', { config: testConfig as any });
    const template = Template.fromStack(stack);
    template.resourceCountIs('AWS::CloudWatch::Dashboard', 1);
  });

  it('should create Lambda functions', () => {
    const app = new App();
    const stack = new AlarmDashboardStack(app, 'TestAlarmDashboardStack3', { config: testConfig as any });
    const template = Template.fromStack(stack);
    // Should have 3 Lambda functions: ddbHandler, configurationHandler, alarmView, alarmList
    const resources = template.toJSON().Resources;
    const lambdas = Object.values(resources).filter((r: any) => r.Type === 'AWS::Lambda::Function');
    expect(lambdas.length).toBe(4);
  });

  it('should create a DynamoDB table', () => {
    const app = new App();
    const stack = new AlarmDashboardStack(app, 'TestAlarmDashboardStack4', { config: testConfig as any });
    const template = Template.fromStack(stack);
    template.resourceCountIs('AWS::DynamoDB::Table', 1);
  });

  it('should create an EventBus', () => {
    const app = new App();
    const stack = new AlarmDashboardStack(app, 'TestAlarmDashboardStack5', { config: testConfig as any });
    const template = Template.fromStack(stack);
    template.resourceCountIs('AWS::Events::EventBus', 1);
  });
});
