"""
Configuration Handler Lambda
Manages dashboard configuration changes (filters, sorting) and alarm suppression/unsuppression.
"""

import os
import sys
import json

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from shared.utils import (
    get_parameter_from_store, put_parameter_to_store,
    apply_filters_from_event, safe_html, validate_account_id
)

ssm_client = boto3.client('ssm')


def handle_suppression_request(event, config):
    """Suppress an alarm so it doesn't show on the dashboard widgets."""
    dynamodb = boto3.resource('dynamodb')
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)

    alarm_key = event['suppress']

    # Validate alarm key format: {account}#{name}#{region}
    parts = alarm_key.split('#')
    if len(parts) < 2:
        return '<pre>Error: Invalid alarm key format.</pre>'

    table.update_item(
        Key={'alarmKey': alarm_key},
        UpdateExpression='SET suppressed = :suppressed',
        ExpressionAttributeValues={':suppressed': 1},
        ReturnValues="ALL_NEW"
    )

    return f'<pre>The Alarm "{safe_html(alarm_key)}" has been suppressed. It will not appear on the dashboard.</pre>'


def handle_unsuppression_request(event, config):
    """Unsuppress an alarm so it shows on the dashboard widgets again."""
    dynamodb = boto3.resource('dynamodb')
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)

    alarm_key = event['unsuppress']

    # Validate alarm key format
    parts = alarm_key.split('#')
    if len(parts) < 2:
        return '<pre>Error: Invalid alarm key format.</pre>'

    table.update_item(
        Key={'alarmKey': alarm_key},
        UpdateExpression='SET suppressed = :suppressed',
        ExpressionAttributeValues={':suppressed': 0},
        ReturnValues="ALL_NEW"
    )

    return f'<pre>The Alarm "{safe_html(alarm_key)}" has been unsuppressed. It will appear on the dashboard again.</pre>'


def lambda_handler(event, context):
    """
    Handle configuration changes, suppressions, and unsuppressions.
    """
    print(f'Event: {json.dumps(event, default=str)}')

    param_name = os.environ.get('CONFIG_PARAMETER_NAME', 'CloudWatchAlarmWidgetConfigCDK')
    config = json.loads(get_parameter_from_store(param_name))

    # Handle suppression request
    if 'suppress' in event:
        return handle_suppression_request(event, config)

    # Handle unsuppression request
    if 'unsuppress' in event:
        return handle_unsuppression_request(event, config)

    # Handle filter/config changes
    config, changed = apply_filters_from_event(event, config)

    message = "Configuration applied:"
    if 'region_filter' in config:
        message += f" region_filter={config['region_filter']}"
    if 'account_filter' in config:
        message += f" account_filter={config['account_filter']}"
    if 'sort_by_region' in config:
        message += f" sort_by_region={config['sort_by_region']}"
    if 'sort_by_account' in config:
        message += f" sort_by_account={config['sort_by_account']}"
    if 'state_filter' in config:
        message += f" state_filter={config['state_filter']}"
    if 'priority_filter' in config:
        message += f" priority_filter={config['priority_filter']}"

    if changed:
        put_parameter_to_store(param_name, json.dumps(config))

    return message
