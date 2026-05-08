import json
import os
import time
import boto3
from html import escape as html_escape
from botocore.exceptions import ClientError
from botocore.config import Config

dynamodb = boto3.resource('dynamodb')
ssm_client = boto3.client('ssm')

# Module-level cache for current account ID (persists across warm starts)
_current_account_id = None

# Module-level cache for assumed role credentials: {(account_id, region): (credentials, expiry_time)}
_credentials_cache = {}

# Cache for SSM config: (value, timestamp)
_config_cache = (None, 0)
CONFIG_CACHE_TTL = 60  # seconds


def get_current_account_id(region='us-east-1'):
    """Get current account ID with module-level caching."""
    global _current_account_id
    if _current_account_id is None:
        boto_config = Config(region_name=region)
        sts_client = boto3.client('sts', config=boto_config)
        _current_account_id = sts_client.get_caller_identity()['Account']
    return _current_account_id


def get_config():
    """Get config from SSM with short TTL cache or from environment variables for static config."""
    global _config_cache

    # Use env var for table name if available (static config)
    table_name = os.environ.get('DYNAMO_TABLE_NAME')
    if table_name:
        now = time.time()
        if _config_cache[0] is not None and (now - _config_cache[1]) < CONFIG_CACHE_TTL:
            return _config_cache[0]
        # Still read SSM for mutable config but merge with env vars
        config = json.loads(get_parameter_from_store(
            os.environ.get('CONFIG_PARAMETER_NAME', 'CloudWatchAlarmWidgetConfigCDK')
        ))
        config['dynamoTableName'] = table_name
        _config_cache = (config, now)
        return config

    # Fallback: read everything from SSM
    return json.loads(get_parameter_from_store('CloudWatchAlarmWidgetConfigCDK'))


def get_parameter_from_store(param_name):
    """Retrieve a parameter from SSM Parameter Store."""
    response = ssm_client.get_parameter(
        Name=param_name,
        WithDecryption=True
    )
    return response['Parameter']['Value']


def is_expression_alarm(alarm):
    """Check if alarm uses metric math expressions."""
    for metric in alarm["detail"]["configuration"]["metrics"]:
        if 'expression' in metric:
            return True
    return False


def get_alarm_type(alarm):
    """Determine alarm type: composite, expression, or standard."""
    if "metrics" not in alarm["detail"]["configuration"]:
        return "composite"
    elif is_expression_alarm(alarm):
        return "expression"
    else:
        return "standard"


def get_cached_credentials(account_id, region):
    """Get cached assumed role credentials, refreshing if expired."""
    cache_key = (account_id, region)
    now = time.time()

    if cache_key in _credentials_cache:
        credentials, expiry = _credentials_cache[cache_key]
        # Refresh 5 minutes before actual expiry
        if now < expiry - 300:
            return credentials

    # Assume role and cache
    boto_config = Config(region_name=region)
    sts_client = boto3.client('sts', config=boto_config)
    target_role = f'arn:aws:iam::{account_id}:role/CrossAccountAlarmAugmentationAssumeRole-{region}'

    assumed_role_object = sts_client.assume_role(
        RoleArn=target_role,
        RoleSessionName="AlarmAugmentationSession"
    )

    credentials = assumed_role_object['Credentials']
    # STS credentials expire in 1 hour by default
    expiry = now + 3600
    _credentials_cache[cache_key] = (credentials, expiry)
    return credentials


def get_client(service, event_account_id, region):
    """Get a boto3 client, using assumed role for cross-account access."""
    boto_config = Config(region_name=region)
    current_account_id = get_current_account_id(region)

    if current_account_id == event_account_id:
        print('Using local execution role')
        return boto3.client(service, config=boto_config)
    else:
        print(f'Using cross-account role for account {event_account_id}')
        credentials = get_cached_credentials(event_account_id, region)
        return boto3.client(
            service,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            config=boto_config
        )


def get_resource_type(metrics):
    """Identify the resource type from metric dimensions."""
    for metric in metrics:
        if "metricStat" not in metric:
            continue
        for dimension in metric["metricStat"]["metric"]["dimensions"].keys():
            if dimension == 'InstanceId':
                return "ec2_instance"
            elif dimension == 'TableName':
                return "ddb_table"
    return "Unknown"


def get_alarm_tags(alarm_arn, account_id, region):
    """Get tags for a CloudWatch alarm."""
    cw_client = get_client('cloudwatch', account_id, region)
    response = cw_client.list_tags_for_resource(ResourceARN=alarm_arn)
    return response['Tags']


def get_priority(alarm_tags):
    """Determine alarm priority from tags. Returns 1 (critical), 2 (medium), or 3 (low)."""
    priority = 2
    for tag in alarm_tags:
        if tag['Key'].lower() == 'priority':
            value = tag['Value'].lower()
            if value in ('high', 'critical', 'urgent'):
                priority = 1
            elif value in ('medium', 'standard', 'normal'):
                priority = 2
            elif value == 'low':
                priority = 3
            break
    return priority


def get_alternate_contact(account_id, region):
    """Get the operations alternate contact for an account."""
    try:
        acct_client = get_client('account', account_id, region)
        result = acct_client.get_alternate_contact(AlternateContactType='OPERATIONS')
        return result['AlternateContact']
    except Exception as e:
        print(f'WARNING: Could not retrieve alternate contact for {account_id}: {e}')
        return {}


def get_ec2_instance_info(account_id, instance_id, region):
    """Get EC2 instance details."""
    print(f'Getting info for instance {instance_id} in account {account_id}, region {region}')
    try:
        ec2_client = get_client('ec2', account_id, region)
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        return response['Reservations'][0]['Instances'][0]
    except Exception as e:
        print(f'WARNING: Could not retrieve instance info for {instance_id}: {e}')
        return {}


def get_account_info(account_id, region):
    """Get AWS Organizations account info."""
    try:
        organizations_client = get_client('organizations', account_id, region)
        result = organizations_client.describe_account(AccountId=account_id)
        if 'JoinedTimestamp' in result['Account']:
            del result['Account']['JoinedTimestamp']
        return result['Account']
    except Exception as e:
        print(f'WARNING: Could not retrieve account info for {account_id}: {e}')
        return {}


def augment_event(event):
    """
    Augment alarm event with additional context.
    Each augmentation step is wrapped in try/except to ensure partial failures
    don't prevent the alarm from being stored.
    """
    payload = event
    region = event['region']
    payload['AlarmName'] = event['detail']['alarmName']

    account_id = event['account']
    payload['Account'] = account_id
    alarm_arn = event['resources'][0]

    # Augment: Alarm tags and priority
    try:
        payload['AlarmTags'] = get_alarm_tags(alarm_arn, account_id, region)
        payload['Priority'] = get_priority(payload['AlarmTags'])
    except Exception as e:
        print(f'ERROR: Failed to get alarm tags for {alarm_arn}: {e}')
        payload['AlarmTags'] = []
        payload['Priority'] = 2  # Default medium

    # Augment: Auxiliary info
    payload['AuxiliaryInfo'] = {}

    # Augment: Alternate contact
    try:
        payload['AuxiliaryInfo']['AlternateContact'] = get_alternate_contact(account_id, region)
    except Exception as e:
        print(f'ERROR: Failed to get alternate contact for {account_id}: {e}')
        payload['AuxiliaryInfo']['AlternateContact'] = {}

    # Augment: Account info
    try:
        payload['AuxiliaryInfo']['Account'] = get_account_info(account_id, region)
    except Exception as e:
        print(f'ERROR: Failed to get account info for {account_id}: {e}')
        payload['AuxiliaryInfo']['Account'] = {}

    # Augment: EC2 instance info (only for standard alarms with EC2 dimensions)
    try:
        if get_alarm_type(event) == "standard":
            if get_resource_type(event['detail']['configuration']['metrics']) == 'ec2_instance':
                instance_id = ''
                for metric in event["detail"]["configuration"]["metrics"]:
                    if "metricStat" in metric:
                        for dimension, value in metric["metricStat"]["metric"]["dimensions"].items():
                            if dimension == 'InstanceId':
                                instance_id = value
                if instance_id:
                    instance_info = get_ec2_instance_info(account_id, instance_id, region)
                    if len(instance_info) == 0:
                        payload['InstanceInfo'] = {'Error': 'Instance not found'}
                    else:
                        payload['InstanceInfo'] = instance_info
    except Exception as e:
        print(f'ERROR: Failed to augment EC2 instance info: {e}')
        payload['InstanceInfo'] = {'Error': f'Augmentation failed: {str(e)}'}

    # Ensure account info has at minimum the account ID
    if not payload['AuxiliaryInfo'].get('Account'):
        payload['AuxiliaryInfo']['Account'] = {'Id': account_id}

    return payload


def lambda_handler(event, context):
    """
    Process CloudWatch Alarm state change events.
    Augments the event with cross-account info and stores in DynamoDB.
    """
    config = get_config()
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)

    event['AuxiliaryInfo'] = {}
    event = augment_event(event)
    event['AuxiliaryInfo']['Suppressed'] = 0

    region = event['region']
    alarm_key = f"{event['account']}#{event['detail']['alarmName']}#{region}"

    state_value = event['detail']['state']['value']
    update_expression = ("SET stateValue = :state_value, "
                         "suppressed = if_not_exists(suppressed, :suppressed), "
                         "detail = :detail, auxiliaryInfo = :auxiliary, "
                         "lastUpdated = :last_updated")
    expression_attribute_values = {
        ':state_value': state_value,
        ':suppressed': 0,
        ':detail': event['detail'],
        ':auxiliary': event['AuxiliaryInfo'],
        ':last_updated': int(time.time())
    }

    # Store InstanceInfo at top-level (consistent with how alarm_view reads it)
    if 'InstanceInfo' in event:
        update_expression += ', instanceInfo = :instance_info'
        expression_attribute_values[':instance_info'] = event['InstanceInfo']

    if 'AlarmTags' in event:
        update_expression += ', alarmTags = :alarm_tags'
        expression_attribute_values[':alarm_tags'] = event['AlarmTags']

    if 'Priority' in event:
        update_expression += ', priority = :priority'
        expression_attribute_values[':priority'] = event['Priority']

    # Critical: wrap DynamoDB write in try/except and re-raise to trigger EventBridge retry
    try:
        response = table.update_item(
            Key={'alarmKey': alarm_key},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW"
        )
        print(f"DynamoDB update successful for alarm: {alarm_key}")
    except ClientError as e:
        print(f"CRITICAL: DynamoDB write failed for {alarm_key}: {e}")
        raise  # Re-raise to trigger EventBridge/Lambda retry
    except Exception as e:
        print(f"CRITICAL: Unexpected error writing to DynamoDB for {alarm_key}: {e}")
        raise  # Re-raise to trigger retry
