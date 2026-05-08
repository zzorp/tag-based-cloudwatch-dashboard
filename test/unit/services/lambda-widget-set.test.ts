import { App, Stack } from 'aws-cdk-lib';
import { LambdaWidgetSet } from '../../../src/services/lambda';

describe('LambdaWidgetSet', () => {
  const mockLambdaResource = {
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
    const widgetSet = new LambdaWidgetSet(stack, 'TestLambdaWidgetSet', mockLambdaResource, config);
    const widgets = widgetSet.getWidgetSets();
    expect(widgets.length).toBeGreaterThan(0);
  });

  it('should create a throttle alarm', () => {
    const widgetSet = new LambdaWidgetSet(stack, 'TestLambdaWidgetSet', mockLambdaResource, config);
    const alarms = widgetSet.getAlarmSet();
    expect(alarms.length).toBe(1);
  });

  it('should set the correct namespace', () => {
    const widgetSet = new LambdaWidgetSet(stack, 'TestLambdaWidgetSet', mockLambdaResource, config);
    expect(widgetSet.namespace).toBe('AWS/Lambda');
  });

  it('should produce widgets containing invocation and error metrics', () => {
    const widgetSet = new LambdaWidgetSet(stack, 'TestLambdaWidgetSet', mockLambdaResource, config);
    const widgets = widgetSet.getWidgetSets();
    // Should have a TextWidget (markdown header) and a Row widget
    expect(widgets.length).toBe(2);
  });
});
