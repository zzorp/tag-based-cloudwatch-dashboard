import * as path from 'path';

// Mock loadConfig before importing the stack module
jest.mock('../../config/config.schema', () => ({
  loadConfig: () => ({
    BaseName: 'TestApp',
    ResourceFile: path.resolve(__dirname, '../fixtures/sample-resources.json'),
    TagKey: 'environment',
    TagValues: ['production'],
    Regions: ['us-east-1'],
    GroupingTagKey: '',
    CustomEC2TagKeys: [],
    CustomNamespaceFile: path.resolve(__dirname, '../fixtures/custom_namespaces.json'),
    Compact: false,
    CompactMaxResourcesPerWidget: 10,
    AlarmTopic: '',
    AlarmDashboard: { enabled: false, organizationId: '', alarmViewListSize: 100 },
    MetricDashboards: { enabled: true },
  }),
}));

import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { IemDashboardStack } from '../../src/stacks/metric-dashboard-stack';

describe('MetricDashboardStack Snapshot', () => {
  it('should match the snapshot', () => {
    const app = new App();
    const stack = new IemDashboardStack(app, 'TestMetricDashboardStack');
    const template = Template.fromStack(stack);
    expect(template.toJSON()).toMatchSnapshot();
  });

  it('should create CloudWatch dashboards', () => {
    const app = new App();
    const stack = new IemDashboardStack(app, 'TestMetricDashboardStack2');
    const template = Template.fromStack(stack);
    template.resourceCountIs('AWS::CloudWatch::Dashboard', 2);
  });

  it('should create CloudWatch alarms', () => {
    const app = new App();
    const stack = new IemDashboardStack(app, 'TestMetricDashboardStack3');
    const template = Template.fromStack(stack);
    // Lambda throttle alarm + DynamoDB write alarm = at least 2 alarms
    const resources = template.toJSON().Resources;
    const alarms = Object.values(resources).filter((r: any) => r.Type === 'AWS::CloudWatch::Alarm');
    expect(alarms.length).toBeGreaterThanOrEqual(2);
  });
});
