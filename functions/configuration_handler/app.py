"""Configuration Handler - manages filters, suppression, and unsuppression."""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from shared.utils import get_parameter_from_store, put_parameter_to_store, apply_filters_from_event, safe_html


def handle_suppression_request(event, config):
    dynamodb = boto3.resource('dynamodb')
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)
    alarm_key = event['suppress']

    table.update_item(
        Key={'alarmKey': alarm_key},
        UpdateExpression='SET suppressed = :suppressed',
        ExpressionAttributeValues={':suppressed': 1},
        ReturnValues="ALL_NEW",
    )
    return f'<pre>Alarm "{safe_html(alarm_key)}" has been suppressed.</pre>'


def handle_unsuppression_request(event, config):
    dynamodb = boto3.resource('dynamodb')
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)
    alarm_key = event['unsuppress']

    table.update_item(
        Key={'alarmKey': alarm_key},
        UpdateExpression='SET suppressed = :suppressed',
        ExpressionAttributeValues={':suppressed': 0},
        ReturnValues="ALL_NEW",
    )
    return f'<pre>Alarm "{safe_html(alarm_key)}" has been unsuppressed.</pre>'


def lambda_handler(event, context):
    print(f'Event: {json.dumps(event, default=str)}')
    param_name = os.environ.get('CONFIG_PARAMETER_NAME', 'CloudWatchAlarmWidgetConfigCDK')
    config = json.loads(get_parameter_from_store(param_name))

    if 'suppress' in event:
        return handle_suppression_request(event, config)
    if 'unsuppress' in event:
        return handle_unsuppression_request(event, config)

    config, changed = apply_filters_from_event(event, config)

    message = "Configuration applied."
    if changed:
        put_parameter_to_store(param_name, json.dumps(config))

    return message
