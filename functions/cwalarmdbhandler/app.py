import json
import os
import sys
import time
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.utils import get_config, safe_html

dynamodb = boto3.resource('dynamodb')

# Module-level cache for current account ID
_current_account_id = None
# Cache for assumed role credentials: {(account_id, region): (credentials, expiry)}
_credentials_cache = {}


def get_current_account_id(region='us-east-1'):
    global _current_account_id
    if _current_account_id is None:
        sts_client = boto3.client('sts', config=Config(region_name=region))
        _current_account_id = sts_client.get_caller_identity()['Account']
    return _current_account_id


def get_cached_credentials(account_id, region):
    cache_key = (account_id, region)
    now = time.time()
    if cache_key in _credentials_cache:
        credentials, expiry = _credentials_cache[cache_key]
        if now < expiry - 300:
            return credentials

    boto_config = Config(region_name=region)
    sts_client = boto3.client('sts', config=boto_config)
    target_role = f'arn:aws:iam::{account_id}:role/CrossAccountAlarmAugmentationAssumeRole-{region}'
    assumed = sts_client.assume_role(RoleArn=target_role, RoleSessionName="AlarmAugmentation")
    credentials = assumed['Credentials']
    _credentials_cache[cache_key] = (credentials, now + 3600)
    return credentials


def get_client(service, event_account_id, region):
    boto_config = Config(region_name=region)
    current = get_current_account_id(region)
    if current == event_account_id:
        return boto3.client(service, config=boto_config)
    else:
        creds = get_cached_credentials(event_account_id, region)
        return boto3.client(
            service,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            config=boto_config,
        )


def is_expression_alarm(alarm):
    for metric in alarm["detail"]["configuration"]["metrics"]:
        if 'expression' in metric:
            return True
    return False


def get_alarm_type(alarm):
    if "metrics" not in alarm["detail"]["configuration"]:
        return "composite"
    elif is_expression_alarm(alarm):
        return "expression"
    else:
        return "standard"


def get_resource_type(metrics):
    for metric in metrics:
        if "metricStat" not in metric:
            continue
        for dimension in metric["metricStat"]["metric"]["dimensions"].keys():
            if dimension == 'InstanceId':
                return "ec2_instance"
            elif dimension == 'TableName':
                return "ddb_table"
    return "Unknown"


def get_priority(alarm_tags):
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


def get_alarm_tags(alarm_arn, account_id, region):
    cw_client = get_client('cloudwatch', account_id, region)
    return cw_client.list_tags_for_resource(ResourceARN=alarm_arn)['Tags']


def get_alternate_contact(account_id, region):
    try:
        acct_client = get_client('account', account_id, region)
        return acct_client.get_alternate_contact(AlternateContactType='OPERATIONS')['AlternateContact']
    except Exception as e:
        print(f'WARNING: No alternate contact for {account_id}: {e}')
        return {}


def get_ec2_instance_info(account_id, instance_id, region):
    try:
        ec2_client = get_client('ec2', account_id, region)
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        return response['Reservations'][0]['Instances'][0]
    except Exception as e:
        print(f'WARNING: No instance info for {instance_id}: {e}')
        return {}


def get_account_info(account_id, region):
    try:
        org_client = get_client('organizations', account_id, region)
        result = org_client.describe_account(AccountId=account_id)
        if 'JoinedTimestamp' in result['Account']:
            del result['Account']['JoinedTimestamp']
        return result['Account']
    except Exception as e:
        print(f'WARNING: No account info for {account_id}: {e}')
        return {}


def augment_event(event):
    payload = event
    region = event['region']
    account_id = event['account']
    alarm_arn = event['resources'][0]

    # Alarm tags (with error resilience)
    try:
        payload['AlarmTags'] = get_alarm_tags(alarm_arn, account_id, region)
        payload['Priority'] = get_priority(payload['AlarmTags'])
    except Exception as e:
        print(f'ERROR: Failed to get alarm tags: {e}')
        payload['AlarmTags'] = []
        payload['Priority'] = 2

    payload['AuxiliaryInfo'] = {}

    try:
        payload['AuxiliaryInfo']['AlternateContact'] = get_alternate_contact(account_id, region)
    except Exception as e:
        print(f'ERROR: Failed alternate contact: {e}')
        payload['AuxiliaryInfo']['AlternateContact'] = {}

    try:
        payload['AuxiliaryInfo']['Account'] = get_account_info(account_id, region)
    except Exception as e:
        print(f'ERROR: Failed account info: {e}')
        payload['AuxiliaryInfo']['Account'] = {}

    try:
        if get_alarm_type(event) == "standard":
            if get_resource_type(event['detail']['configuration']['metrics']) == 'ec2_instance':
                instance_id = ''
                for metric in event["detail"]["configuration"]["metrics"]:
                    if "metricStat" in metric:
                        for dim, val in metric["metricStat"]["metric"]["dimensions"].items():
                            if dim == 'InstanceId':
                                instance_id = val
                if instance_id:
                    info = get_ec2_instance_info(account_id, instance_id, region)
                    payload['InstanceInfo'] = info if info else {'Error': 'Instance not found'}
    except Exception as e:
        print(f'ERROR: Failed EC2 augmentation: {e}')

    if not payload['AuxiliaryInfo'].get('Account'):
        payload['AuxiliaryInfo']['Account'] = {'Id': account_id}

    return payload


def lambda_handler(event, context):
    config = get_config()
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)

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
        ':last_updated': int(time.time()),
    }

    if 'InstanceInfo' in event:
        update_expression += ', instanceInfo = :instance_info'
        expression_attribute_values[':instance_info'] = event['InstanceInfo']

    if 'AlarmTags' in event:
        update_expression += ', alarmTags = :alarm_tags'
        expression_attribute_values[':alarm_tags'] = event['AlarmTags']

    if 'Priority' in event:
        update_expression += ', priority = :priority'
        expression_attribute_values[':priority'] = event['Priority']

    try:
        table.update_item(
            Key={'alarmKey': alarm_key},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW",
        )
        print(f"DynamoDB update successful for: {alarm_key}")
    except Exception as e:
        print(f"CRITICAL: DynamoDB write failed for {alarm_key}: {e}")
        raise
