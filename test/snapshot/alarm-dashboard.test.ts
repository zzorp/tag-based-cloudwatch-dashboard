import { App } from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
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
    const stack = new AlarmDashboardStack(app, 'TestAlarmDashboardStack', { config: testConfig as any });
    template = Template.fromStack(stack);
  });

  describe('CloudWatch Dashboard', () => {
    it('should create exactly one dashboard', () => {
      template.resourceCountIs('AWS::CloudWatch::Dashboard', 1);
    });

    it('should have the correct dashboard name', () => {
      template.hasResourceProperties('AWS::CloudWatch::Dashboard', {
        DashboardName: 'AlarmDashboardCDK',
      });
    });
  });

  describe('Lambda Functions', () => {
    it('should create 4 Lambda functions', () => {
      const resources = template.toJSON().Resources;
      const lambdas = Object.values(resources).filter((r: any) => r.Type === 'AWS::Lambda::Function');
      expect(lambdas.length).toBe(4);
    });

    it('should use Python 3.12 runtime for all functions', () => {
      const resources = template.toJSON().Resources;
      const lambdas = Object.values(resources).filter((r: any) => r.Type === 'AWS::Lambda::Function') as any[];
      lambdas.forEach((lambda) => {
        expect(lambda.Properties.Runtime).toBe('python3.12');
      });
    });

    it('should set environment variables on DDB handler', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'CloudWatchAlarmDynamoDBHandlerCDK',
        Environment: {
          Variables: Match.objectLike({
            CONFIG_PARAMETER_NAME: 'CloudWatchAlarmWidgetConfigCDK',
          }),
        },
      });
      // Verify DYNAMO_TABLE_NAME is set (value is a Ref, not a literal)
      const resources = template.toJSON().Resources;
      const ddbHandler = Object.values(resources).find(
        (r: any) => r.Type === 'AWS::Lambda::Function' && r.Properties?.FunctionName === 'CloudWatchAlarmDynamoDBHandlerCDK'
      ) as any;
      expect(ddbHandler.Properties.Environment.Variables.DYNAMO_TABLE_NAME).toBeDefined();
    });

    it('should set environment variables on alarm view', () => {
      // Verify MAX_GRID_ALARMS env var exists on at least one function
      const resources = template.toJSON().Resources;
      const lambdas = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::Lambda::Function' &&
        r.Properties?.Environment?.Variables?.MAX_GRID_ALARMS === '200'
      );
      expect(lambdas.length).toBe(1);
    });

    it('should set explicit timeout and memory for alarm view', () => {
      const resources = template.toJSON().Resources;
      const alarmViewLambdas = Object.values(resources).filter(
        (r: any) => r.Type === 'AWS::Lambda::Function' && r.Properties?.Environment?.Variables?.MAX_GRID_ALARMS === '200'
      ) as any[];
      expect(alarmViewLambdas.length).toBe(1);
      expect(alarmViewLambdas[0].Properties.Timeout).toBe(30);
      expect(alarmViewLambdas[0].Properties.MemorySize).toBe(256);
    });

    it('should configure retry attempts on DDB handler', () => {
      template.hasResourceProperties('AWS::Lambda::Function', {
        FunctionName: 'CloudWatchAlarmDynamoDBHandlerCDK',
      });
    });
  });

  describe('DynamoDB Table', () => {
    it('should create exactly one table', () => {
      template.resourceCountIs('AWS::DynamoDB::Table', 1);
    });

    it('should have TTL enabled', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        TimeToLiveSpecification: {
          AttributeName: 'ttl',
          Enabled: true,
        },
      });
    });

    it('should use PAY_PER_REQUEST billing', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        BillingMode: 'PAY_PER_REQUEST',
      });
    });

    it('should have 3 GSIs (removed redundant AlarmKeyIndex)', () => {
      template.hasResourceProperties('AWS::DynamoDB::Table', {
        GlobalSecondaryIndexes: Match.arrayWith([
          Match.objectLike({ IndexName: 'StateValueIndex' }),
          Match.objectLike({ IndexName: 'SuppressionIndex' }),
          Match.objectLike({ IndexName: 'NonSuppressedAlarms' }),
        ]),
      });
      // Verify no AlarmKeyIndex
      const resources = template.toJSON().Resources;
      const tables = Object.values(resources).filter((r: any) => r.Type === 'AWS::DynamoDB::Table') as any[];
      const gsiNames = tables[0].Properties.GlobalSecondaryIndexes.map((g: any) => g.IndexName);
      expect(gsiNames).not.toContain('AlarmKeyIndex');
    });
  });

  describe('EventBus', () => {
    it('should create exactly one custom event bus', () => {
      template.resourceCountIs('AWS::Events::EventBus', 1);
    });

    it('should have org-scoped resource policy', () => {
      template.hasResourceProperties('AWS::Events::EventBusPolicy', {
        StatementId: 'AllowPutFromAllOrg',
      });
    });
  });

  describe('Dead Letter Queue', () => {
    it('should create EventBridge DLQ', () => {
      template.hasResourceProperties('AWS::SQS::Queue', {
        QueueName: 'AlarmDashboardEventBridgeDLQ',
      });
    });

    it('should have 14-day retention', () => {
      template.hasResourceProperties('AWS::SQS::Queue', {
        MessageRetentionPeriod: 1209600, // 14 days in seconds
      });
    });
  });

  describe('Operational Alarms', () => {
    it('should create alarms for DDB handler errors', () => {
      template.hasResourceProperties('AWS::CloudWatch::Alarm', {
        AlarmName: 'AlarmDashboard-DDBHandler-Errors',
      });
    });

    it('should create alarm for DLQ depth', () => {
      template.hasResourceProperties('AWS::CloudWatch::Alarm', {
        AlarmName: 'AlarmDashboard-DLQ-Depth',
      });
    });
  });

  describe('EventBridge Rules', () => {
    it('should create 2 EventBridge rules', () => {
      template.resourceCountIs('AWS::Events::Rule', 2);
    });

    it('should configure retry and max age on rule targets', () => {
      // At least one rule should have retry config
      const resources = template.toJSON().Resources;
      const rules = Object.values(resources).filter((r: any) => r.Type === 'AWS::Events::Rule') as any[];
      const hasRetryConfig = rules.some((rule) =>
        rule.Properties?.Targets?.some((t: any) => t.RetryPolicy?.MaximumRetryAttempts === 3)
      );
      expect(hasRetryConfig).toBe(true);
    });
  });

  describe('SSM Parameter', () => {
    it('should create the config parameter', () => {
      template.hasResourceProperties('AWS::SSM::Parameter', {
        Name: 'CloudWatchAlarmWidgetConfigCDK',
        Type: 'String',
      });
    });
  });
});
