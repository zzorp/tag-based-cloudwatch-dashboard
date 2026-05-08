import * as cdk from 'aws-cdk-lib';
import { Aws, CfnOutput, Duration, RemovalPolicy, Tags } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { EventBus, EventBusPolicy, Rule } from 'aws-cdk-lib/aws-events';
import { Effect, PolicyStatement, Role, ServicePrincipal, StarPrincipal } from 'aws-cdk-lib/aws-iam';
import { AttributeType, BillingMode, ProjectionType, Table } from 'aws-cdk-lib/aws-dynamodb';
import { Architecture, Code, Function, Runtime, Tracing } from 'aws-cdk-lib/aws-lambda';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { CustomWidget, Dashboard, Alarm, Metric, ComparisonOperator, TreatMissingData } from 'aws-cdk-lib/aws-cloudwatch';
import { Queue } from 'aws-cdk-lib/aws-sqs';
import { NagSuppressions } from 'cdk-nag';
import { loadConfig } from '../../config/config.schema';
import { AppConfig } from '../types/config';

export interface AlarmDashboardStackProps extends cdk.StackProps {
  config?: AppConfig;
}

export class AlarmDashboardStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: AlarmDashboardStackProps) {
    super(scope, id, props);

    const config = props?.config ?? loadConfig();
    const organizationId = config['AlarmDashboard']['organizationId'];
    const parameterConfig: any = {};

    // ========================================
    // Dead Letter Queue for failed EventBridge events
    // ========================================
    const eventBridgeDLQ = new Queue(this, 'AlarmDashboardEventBridgeDLQ', {
      queueName: 'AlarmDashboardEventBridgeDLQ',
      retentionPeriod: Duration.days(14),
      visibilityTimeout: Duration.seconds(300),
    });

    // ========================================
    // EventBus
    // ========================================
    const cloudwatchEventBus = new EventBus(this, 'CloudWatchEventBus', {
      eventBusName: 'CWAlarmEventBusCDK',
    });

    const busResourcePolicy = new PolicyStatement({
      sid: 'AllowPutFromAllOrg',
      effect: Effect.ALLOW,
      principals: [new StarPrincipal()],
      actions: ['events:PutEvents'],
      resources: [cloudwatchEventBus.eventBusArn],
      conditions: {
        StringEquals: {
          'aws:PrincipalOrgId': organizationId,
        },
      },
    });

    new EventBusPolicy(this, 'CloudWatchEventBusPolicy', {
      eventBus: cloudwatchEventBus,
      statementId: 'AllowPutFromAllOrg',
      statement: busResourcePolicy.toStatementJson(),
    });

    // ========================================
    // DynamoDB Table
    // ========================================
    const dynamoTable = new Table(this, 'CloudWatchAlarmDynamoDBTable', {
      tableName: 'AlarmStateChangeTableCDK',
      partitionKey: { name: 'alarmKey', type: AttributeType.STRING },
      removalPolicy: RemovalPolicy.DESTROY,
      billingMode: BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl', // TTL attribute for auto-expiring old records
    });

    parameterConfig['dynamoTableARN'] = dynamoTable.tableArn;
    parameterConfig['dynamoTableName'] = dynamoTable.tableName;
    parameterConfig['eventBusARN'] = cloudwatchEventBus.eventBusArn;

    Tags.of(dynamoTable).add('auto-delete', 'never');

    // GSI: StateValueIndex - query by alarm state
    dynamoTable.addGlobalSecondaryIndex({
      indexName: 'StateValueIndex',
      partitionKey: { name: 'stateValue', type: AttributeType.STRING },
      projectionType: ProjectionType.ALL,
    });

    // GSI: SuppressionIndex - query non-suppressed alarms
    dynamoTable.addGlobalSecondaryIndex({
      indexName: 'SuppressionIndex',
      partitionKey: { name: 'suppressed', type: AttributeType.NUMBER },
      projectionType: ProjectionType.ALL,
    });

    // GSI: NonSuppressedAlarms - query alarms by state that are not suppressed
    dynamoTable.addGlobalSecondaryIndex({
      indexName: 'NonSuppressedAlarms',
      partitionKey: { name: 'stateValue', type: AttributeType.STRING },
      sortKey: { name: 'suppressed', type: AttributeType.NUMBER },
      projectionType: ProjectionType.ALL,
    });

    // NOTE: Removed redundant AlarmKeyIndex GSI (same partition key as table)

    // ========================================
    // Lambda: DynamoDB Handler (event processor)
    // ========================================
    const ddbHandlerLambdaRole = new Role(this, 'CloudWatchAlarmDynamoDBHandlerExecutionRole', {
      description: 'CloudWatchAlarmDynamoDB Handler Role',
      assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
      roleName: 'CloudWatchAlarmDynamoDBHandlerExecutionRole',
    });

    const ddbHandlerLambdaFunction = new Function(this, 'CloudWatchAlarmDynamoDBHandlerFunction', {
      runtime: Runtime.PYTHON_3_12,
      handler: 'app.lambda_handler',
      code: Code.fromAsset('functions/cwalarmdbhandler/'),
      functionName: 'CloudWatchAlarmDynamoDBHandlerCDK',
      timeout: Duration.seconds(60),
      memorySize: 256,
      tracing: Tracing.ACTIVE,
      role: ddbHandlerLambdaRole,
      retryAttempts: 2,
      environment: {
        DYNAMO_TABLE_NAME: dynamoTable.tableName,
        CONFIG_PARAMETER_NAME: 'CloudWatchAlarmWidgetConfigCDK',
      },
    });

    // Logging permissions
    ddbHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
        resources: [`arn:aws:logs:${Aws.REGION}:${Aws.ACCOUNT_ID}:log-group:/aws/lambda/CloudWatchAlarmDynamoDBHandlerCDK:*`],
      }),
    );

    // DynamoDB permissions
    ddbHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['dynamodb:PutItem', 'dynamodb:GetItem', 'dynamodb:UpdateItem', 'dynamodb:GetRecords'],
        resources: [dynamoTable.tableArn],
      }),
    );

    // Organizations and Account permissions (requires * for cross-account)
    ddbHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          'organizations:DescribeAccount',
          'account:GetAlternateContact',
          'account:GetContactInformation',
        ],
        resources: ['*'],
      }),
    );

    // STS AssumeRole for cross-account access
    ddbHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['sts:AssumeRole'],
        resources: ['arn:aws:iam::*:role/CrossAccountAlarmAugmentationAssumeRole-*'],
      }),
    );

    // EC2 describe for instance augmentation
    ddbHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['ec2:DescribeInstances'],
        resources: ['*'],
      }),
    );

    // CloudWatch tag reading
    ddbHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['cloudwatch:ListTagsForResource'],
        resources: [`arn:aws:cloudwatch:*:${Aws.ACCOUNT_ID}:alarm:*`],
      }),
    );

    // ========================================
    // Lambda: Configuration Handler
    // ========================================
    const configurationHandlerLambdaRole = new Role(this, 'CloudWatchAlarmConfigurationHandlerExecutionRole', {
      description: 'CloudWatchAlarm Configuration Handler Role',
      assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
      roleName: 'CloudWatchAlarmConfigurationHandlerExecutionRole',
    });

    const configurationHandlerLambdaFunction = new Function(this, 'configurationHandlerLambdaFunction', {
      runtime: Runtime.PYTHON_3_12,
      handler: 'app.lambda_handler',
      code: Code.fromAsset('functions/configuration_handler/'),
      functionName: 'CloudWatchAlarmConfigurationHandlerCDK',
      timeout: Duration.seconds(60),
      memorySize: 128,
      tracing: Tracing.ACTIVE,
      role: configurationHandlerLambdaRole,
      environment: {
        DYNAMO_TABLE_NAME: dynamoTable.tableName,
        CONFIG_PARAMETER_NAME: 'CloudWatchAlarmWidgetConfigCDK',
      },
    });

    configurationHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
        resources: [`arn:aws:logs:${Aws.REGION}:${Aws.ACCOUNT_ID}:log-group:/aws/lambda/CloudWatchAlarmConfigurationHandlerCDK:*`],
      }),
    );

    configurationHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['dynamodb:UpdateItem'],
        resources: [dynamoTable.tableArn],
      }),
    );

    // ========================================
    // EventBridge Rules
    // ========================================
    new Rule(this, 'DDBHandlerTrigger', {
      eventBus: cloudwatchEventBus,
      eventPattern: {
        source: ['aws.cloudwatch'],
        detailType: ['CloudWatch Alarm State Change'],
      },
      targets: [new LambdaFunction(ddbHandlerLambdaFunction, {
        deadLetterQueue: eventBridgeDLQ,
        retryAttempts: 3,
        maxEventAge: Duration.hours(2),
      })],
    });

    new Rule(this, 'LocalDDBHandlerTrigger', {
      eventPattern: {
        source: ['aws.cloudwatch'],
        detailType: ['CloudWatch Alarm State Change'],
      },
      targets: [new LambdaFunction(ddbHandlerLambdaFunction, {
        deadLetterQueue: eventBridgeDLQ,
        retryAttempts: 3,
        maxEventAge: Duration.hours(2),
      })],
    });

    // ========================================
    // SSM Parameter Store (mutable config)
    // ========================================
    parameterConfig['compact'] = 0;
    parameterConfig['configuratorLambdaFunction'] = configurationHandlerLambdaFunction.functionArn;
    parameterConfig['alarmViewListSize'] = config.AlarmDashboard.alarmViewListSize
      ? config.AlarmDashboard.alarmViewListSize
      : 100;

    const configParameter = new StringParameter(this, 'ConfigParameter', {
      stringValue: JSON.stringify(parameterConfig),
      parameterName: 'CloudWatchAlarmWidgetConfigCDK',
      description: 'Config for CloudWatch Alarm Widgets',
    });

    ddbHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['ssm:GetParameter'],
        resources: [`arn:aws:ssm:${Aws.REGION}:${Aws.ACCOUNT_ID}:parameter/CloudWatchAlarmWidgetConfigCDK`],
      }),
    );

    configurationHandlerLambdaFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['ssm:GetParameter', 'ssm:PutParameter'],
        resources: [`arn:aws:ssm:${Aws.REGION}:${Aws.ACCOUNT_ID}:parameter/CloudWatchAlarmWidgetConfigCDK`],
      }),
    );

    // ========================================
    // Lambda: Alarm View (grid widget)
    // ========================================
    const alarmCWCustomFunctionRole = new Role(this, 'alarmCWCustomFunctionExecutionRole', {
      description: 'alarmCWCustomFunction Handler Role',
      assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
      roleName: 'alarmCWCustomFunctionExecutionRole',
    });

    const alarmCWCustomFunction = new Function(this, 'AlarmCWCustomFunction', {
      code: Code.fromAsset('functions/alarm_view'),
      handler: 'app.lambda_handler',
      runtime: Runtime.PYTHON_3_12,
      architecture: Architecture.X86_64,
      timeout: Duration.seconds(30),
      memorySize: 256,
      role: alarmCWCustomFunctionRole,
      environment: {
        DYNAMO_TABLE_NAME: dynamoTable.tableName,
        CONFIG_PARAMETER_NAME: 'CloudWatchAlarmWidgetConfigCDK',
        MAX_GRID_ALARMS: '200',
      },
    });

    alarmCWCustomFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
        resources: [`arn:aws:logs:${Aws.REGION}:${Aws.ACCOUNT_ID}:log-group:/aws/lambda/*`],
      }),
    );

    alarmCWCustomFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['ssm:GetParameter'],
        resources: [`arn:aws:ssm:${Aws.REGION}:${Aws.ACCOUNT_ID}:parameter/CloudWatchAlarmWidgetConfigCDK`],
      }),
    );

    alarmCWCustomFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          'dynamodb:GetItem',
          'dynamodb:Scan',
          'dynamodb:Query',
          'dynamodb:BatchGetItem',
          'dynamodb:DescribeTable',
        ],
        resources: [
          dynamoTable.tableArn,
          `${dynamoTable.tableArn}/index/StateValueIndex`,
          `${dynamoTable.tableArn}/index/SuppressionIndex`,
          `${dynamoTable.tableArn}/index/NonSuppressedAlarms`,
        ],
      }),
    );

    // ========================================
    // Lambda: Alarm List (table widget)
    // ========================================
    const alarmListCWCustomFunctionRole = new Role(this, 'alarmListCWCustomFunctionRole', {
      description: 'alarmListCWCustomFunction Handler Role',
      assumedBy: new ServicePrincipal('lambda.amazonaws.com'),
      roleName: 'alarmListCWCustomFunctionExecutionRole',
    });

    const alarmListCWCustomFunction = new Function(this, 'AlarmListCWCustomFunction', {
      code: Code.fromAsset('functions/alarm_list'),
      handler: 'app.lambda_handler',
      runtime: Runtime.PYTHON_3_12,
      architecture: Architecture.X86_64,
      timeout: Duration.seconds(30),
      memorySize: 256,
      role: alarmListCWCustomFunctionRole,
      environment: {
        DYNAMO_TABLE_NAME: dynamoTable.tableName,
        CONFIG_PARAMETER_NAME: 'CloudWatchAlarmWidgetConfigCDK',
        CONFIGURATOR_LAMBDA_ARN: configurationHandlerLambdaFunction.functionArn,
      },
    });

    alarmListCWCustomFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
        resources: [`arn:aws:logs:${Aws.REGION}:${Aws.ACCOUNT_ID}:log-group:/aws/lambda/*`],
      }),
    );

    alarmListCWCustomFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          'dynamodb:GetItem',
          'dynamodb:Scan',
          'dynamodb:Query',
          'dynamodb:BatchGetItem',
          'dynamodb:DescribeTable',
        ],
        resources: [
          dynamoTable.tableArn,
          `${dynamoTable.tableArn}/index/StateValueIndex`,
          `${dynamoTable.tableArn}/index/SuppressionIndex`,
          `${dynamoTable.tableArn}/index/NonSuppressedAlarms`,
        ],
      }),
    );

    alarmListCWCustomFunction.addToRolePolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ['ssm:GetParameter', 'ssm:PutParameter'],
        resources: [`arn:aws:ssm:${Aws.REGION}:${Aws.ACCOUNT_ID}:parameter/CloudWatchAlarmWidgetConfigCDK`],
      }),
    );

    // ========================================
    // CloudWatch Dashboard
    // ========================================
    new Dashboard(this, 'AlarmDashboardCDK', {
      dashboardName: 'AlarmDashboardCDK',
      widgets: [
        [
          new CustomWidget({
            functionArn: alarmCWCustomFunction.functionArn,
            title: 'Alarms Overview',
            height: 10,
            width: 24,
            updateOnRefresh: true,
            updateOnResize: true,
            updateOnTimeRangeChange: false,
          }),
        ],
        [
          new CustomWidget({
            functionArn: alarmListCWCustomFunction.functionArn,
            title: 'Alarm List',
            height: 26,
            width: 24,
            updateOnRefresh: true,
            updateOnResize: true,
            updateOnTimeRangeChange: false,
          }),
        ],
      ],
    });

    // ========================================
    // Operational Alarms (monitoring the dashboard infra itself)
    // ========================================
    new Alarm(this, 'DDBHandlerErrorAlarm', {
      alarmName: 'AlarmDashboard-DDBHandler-Errors',
      alarmDescription: 'Alarm Dashboard DDB Handler Lambda is failing',
      metric: ddbHandlerLambdaFunction.metricErrors({
        period: Duration.minutes(5),
      }),
      threshold: 5,
      evaluationPeriods: 2,
      comparisonOperator: ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: TreatMissingData.NOT_BREACHING,
    });

    new Alarm(this, 'DLQDepthAlarm', {
      alarmName: 'AlarmDashboard-DLQ-Depth',
      alarmDescription: 'Alarm Dashboard DLQ has messages (events are being lost)',
      metric: eventBridgeDLQ.metricApproximateNumberOfMessagesVisible({
        period: Duration.minutes(5),
      }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: TreatMissingData.NOT_BREACHING,
    });

    // ========================================
    // cdk-nag suppression rules
    // ========================================
    NagSuppressions.addResourceSuppressions(
      ddbHandlerLambdaRole,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason:
            'CloudWatchAlarmDynamoDBHandlerExecutionRole needs to assume cross-account roles with dynamic naming ' +
            'and describe EC2 instances across accounts. Organizations API requires * resources.',
        },
      ],
      true,
    );

    NagSuppressions.addResourceSuppressions(
      configurationHandlerLambdaRole,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'CloudWatchAlarmConfigurationHandlerExecutionRole scoped to specific log group',
        },
      ],
      true,
    );

    NagSuppressions.addResourceSuppressions(
      alarmCWCustomFunctionRole,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'alarmCWCustomFunctionExecutionRole scoped to specific log group',
        },
      ],
      true,
    );

    NagSuppressions.addResourceSuppressions(
      alarmListCWCustomFunctionRole,
      [
        {
          id: 'AwsSolutions-IAM5',
          reason: 'alarmListCWCustomFunctionExecutionRole scoped to specific log group',
        },
      ],
      true,
    );

    NagSuppressions.addResourceSuppressions(
      dynamoTable,
      [
        {
          id: 'AwsSolutions-DDB3',
          reason: "Alarm data doesn't require PITR - TTL handles cleanup",
        },
      ],
      true,
    );

    NagSuppressions.addResourceSuppressions(
      eventBridgeDLQ,
      [
        {
          id: 'AwsSolutions-SQS3',
          reason: 'This IS the dead letter queue - no further DLQ needed',
        },
        {
          id: 'AwsSolutions-SQS4',
          reason: 'DLQ does not need encryption for alarm event metadata',
        },
      ],
      true,
    );

    // ========================================
    // Outputs
    // ========================================
    new CfnOutput(this, 'CustomEventBusArn', {
      value: cloudwatchEventBus.eventBusArn,
      description: 'ARN of the custom EventBus for cross-account alarm forwarding',
    });

    new CfnOutput(this, 'CustomDynamoDBFunctionRoleArn', {
      value: ddbHandlerLambdaRole.roleArn,
      description: 'ARN of the DDB handler Lambda role (needed for source account stack set)',
    });

    new CfnOutput(this, 'DeadLetterQueueUrl', {
      value: eventBridgeDLQ.queueUrl,
      description: 'URL of the DLQ for failed alarm events',
    });
  }
}
