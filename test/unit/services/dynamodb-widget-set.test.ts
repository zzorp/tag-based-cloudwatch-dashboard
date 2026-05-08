import { App, Stack } from 'aws-cdk-lib';
import { DynamodbWidgetSet } from '../../../src/services/dynamodb';

describe('DynamodbWidgetSet', () => {
  const mockDynamoDBResource = {
    ResourceARN: 'arn:aws:dynamodb:us-east-1:123456789012:table/MyTestTable',
    Tags: [{ Key: 'environment', Value: 'production' }],
    type: 'provisioned',
    wcu: 5,
    rcu: 5,
  };

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

  let stack: Stack;

  beforeEach(() => {
    const app = new App();
    stack = new Stack(app, 'TestStack');
  });

  it('should create widget sets', () => {
    const widgetSet = new DynamodbWidgetSet(stack, 'TestDynamoDBWidgetSet', mockDynamoDBResource, config);
    const widgets = widgetSet.getWidgetSets();
    expect(widgets.length).toBeGreaterThan(0);
  });

  it('should create alarms for write capacity', () => {
    const widgetSet = new DynamodbWidgetSet(stack, 'TestDynamoDBWidgetSet', mockDynamoDBResource, config);
    const alarms = widgetSet.getAlarmSet();
    expect(alarms.length).toBe(1);
  });

  it('should set the correct namespace', () => {
    const widgetSet = new DynamodbWidgetSet(stack, 'TestDynamoDBWidgetSet', mockDynamoDBResource, config);
    expect(widgetSet.namespace).toBe('AWS/DynamoDB');
  });

  it('should produce a Row widget with RCU and WCU graphs', () => {
    const widgetSet = new DynamodbWidgetSet(stack, 'TestDynamoDBWidgetSet', mockDynamoDBResource, config);
    const widgets = widgetSet.getWidgetSets();
    // DynamodbWidgetSet creates one Row with two GraphWidgets
    expect(widgets.length).toBe(1);
  });

  it('should provide a static overall widget', () => {
    const overallWidget = DynamodbWidgetSet.getOverallWidget();
    expect(overallWidget).toBeDefined();
  });
});
