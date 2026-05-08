"""
Alarm View Custom Widget Lambda
Renders a grid visualization of alarms currently in ALARM state.
"""

import os
import sys
import json

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from shared.utils import (
    get_config, get_alarm_type, safe_html, get_info_icon,
    SHARED_CSS
)

dynamodb = boto3.resource('dynamodb')

# Maximum number of alarms to render in the grid to prevent timeout/oversized HTML
MAX_GRID_ALARMS = 200


def sort_by_priority(alarms):
    """Sort alarms by priority, defaulting missing priority to 2 (medium)."""
    for alarm in alarms:
        if 'priority' not in alarm:
            alarm['priority'] = 2
    return sorted(alarms, key=lambda x: x['priority'])


def get_grid_settings(number_of_alarms):
    """Determine grid size and font size based on alarm count."""
    if number_of_alarms <= 30:
        return 10, 12
    elif number_of_alarms <= 60:
        return 15, 10
    elif number_of_alarms <= 80:
        return 20, 9
    else:
        return 25, 8


def build_alarm_detail_html(alarm, alarm_name, account_id, region, auxiliary_info):
    """Build the popup detail HTML for a single alarm."""
    card_html = ''

    # Alternate Contact section
    if 'AlternateContact' in auxiliary_info and auxiliary_info['AlternateContact']:
        card_html += "<h4>Alternate Contact (OPERATIONS)</h4>"
        contact = auxiliary_info['AlternateContact']
        if 'Name' in contact:
            card_html += f'<div>Name: {safe_html(contact["Name"])}</div>'
        if 'Title' in contact:
            card_html += f'<div>Title: {safe_html(contact["Title"])}</div>'
        if 'PhoneNumber' in contact:
            card_html += f'<div>Phone: {safe_html(contact["PhoneNumber"])}</div>'
        if 'EmailAddress' in contact:
            email = safe_html(contact["EmailAddress"])
            card_html += f'<div>Email: <a href="mailto:{email}">{email}</a></div>'
        card_html += '<hr/>'

    # Account Info section
    if 'Account' in auxiliary_info and auxiliary_info['Account']:
        card_html += "<h4>Account Info</h4>"
        acct = auxiliary_info['Account']
        if 'Status' in acct:
            card_html += f'<div>Status: {safe_html(acct["Status"])}</div>'
        if 'Email' in acct:
            email = safe_html(acct["Email"])
            card_html += f'<div>Email: <a href="mailto:{email}">{email}</a></div>'
        if 'Id' in acct:
            card_html += f'<div>Id: {safe_html(acct["Id"])}</div>'
        card_html += f'<div>Region: {safe_html(region)}</div><hr />'

    # Alarm Details section
    card_html += "<h4>Alarm Details</h4>"
    card_html += f'<div>Name: {safe_html(alarm["detail"]["alarmName"])}</div>'
    card_html += f'<div>Current State: {safe_html(alarm["detail"]["state"]["value"])}</div>'
    card_html += f'<div>State Change Timestamp: {safe_html(alarm["detail"]["state"]["timestamp"])}</div>'
    card_html += f'<div>State Change Reason: {safe_html(alarm["detail"]["state"]["reason"])}</div>'
    card_html += '<hr />'

    # Metric Info section
    card_html += '<h4>Metric Info</h4>'
    alarm_type = get_alarm_type(alarm)
    if alarm_type == "composite":
        card_html += '<div>Composite Alarm</div>'
        card_html += f'<div>Alarm Rule: {safe_html(alarm["detail"]["configuration"].get("alarmRule", ""))}</div>'
    elif alarm_type == "expression":
        for metric in alarm["detail"]["configuration"]["metrics"]:
            if 'expression' in metric:
                card_html += f'<div>Expression: {safe_html(metric["expression"])}</div>'
                card_html += f'<div>Label: {safe_html(metric["label"])}</div>'
            if 'metricStat' in metric:
                card_html += f'<div>Namespace: {safe_html(metric["metricStat"]["metric"]["namespace"])}</div>'
                card_html += f'<div>Metric Name: {safe_html(metric["metricStat"]["metric"]["name"])}</div>'
                dims = metric["metricStat"]["metric"].get("dimensions", {})
                if dims:
                    card_html += '<div>Dimensions:</div>'
                    for dim_key, dim_val in dims.items():
                        card_html += f'<div>&nbsp;&nbsp;{safe_html(dim_key)}: {safe_html(dim_val)}</div>'
    elif alarm_type == "standard":
        for metric in alarm["detail"]["configuration"]["metrics"]:
            if "metricStat" in metric:
                card_html += f'<div>Namespace: {safe_html(metric["metricStat"]["metric"]["namespace"])}</div>'
                card_html += f'<div>Metric Name: {safe_html(metric["metricStat"]["metric"]["name"])}</div>'
                dims = metric["metricStat"]["metric"].get("dimensions", {})
                if dims:
                    card_html += '<div>Dimensions:</div>'
                    for dim_key, dim_val in dims.items():
                        card_html += f'<div>&nbsp;&nbsp;{safe_html(dim_key)}: {safe_html(dim_val)}</div>'
    card_html += '<hr />'

    # Instance Info section
    if 'instanceInfo' in alarm:
        if 'Error' not in alarm['instanceInfo']:
            card_html += '<h4>Instance Info</h4>'
            info = alarm['instanceInfo']
            if 'Tags' in info and info['Tags']:
                card_html += '<div><b>Tags:</b></div>'
                for tag in info['Tags']:
                    card_html += f'<div>&nbsp;&nbsp;{safe_html(tag["Key"])}: {safe_html(tag["Value"])}</div>'
            card_html += f'<div><b>Instance ID:</b> {safe_html(info.get("InstanceId", ""))}</div>'
            card_html += f'<div><b>Instance Type:</b> {safe_html(info.get("InstanceType", ""))}</div>'
            card_html += f'<div><b>AMI ID:</b> {safe_html(info.get("ImageId", ""))}</div>'
        else:
            card_html += '<h4>Instance Info</h4>'
            card_html += '<div style="color: var(--alarm-text);">RESOURCE DELETED</div>'
        card_html += '<hr />'

    # Alarm link (using actual region, not hardcoded)
    alarm_name_encoded = safe_html(alarm["detail"]["alarmName"])
    card_html += f'<h4>Alarm Link</h4>'
    card_html += (f'<a href="https://{safe_html(region)}.console.aws.amazon.com/cloudwatch/'
                  f'home?region={safe_html(region)}#alarmsV2:alarm/{alarm_name_encoded}?">'
                  f'View in CloudWatch Console</a>')

    return card_html


def build_grid_item(alarm):
    """Build a single grid item HTML for an alarm."""
    alarm_name = alarm['alarmKey'].split('#')[1]
    account_id = alarm['alarmKey'].split('#')[0]
    region = alarm['alarmKey'].split('#')[2] if len(alarm['alarmKey'].split('#')) > 2 else 'unknown'

    auxiliary_info = alarm.get('auxiliaryInfo', {})
    resource_id = ''
    resource_deleted_mark = ''
    resource_strike_through = ''
    instance_name = ''

    # Get resource ID from metrics
    alarm_type = get_alarm_type(alarm)
    if alarm_type == "standard" and "metrics" in alarm.get("detail", {}).get("configuration", {}):
        for metric in alarm["detail"]["configuration"]["metrics"]:
            if "metricStat" in metric:
                for dim_val in metric["metricStat"]["metric"].get("dimensions", {}).values():
                    resource_id = dim_val
    elif alarm_type == "expression" and "metrics" in alarm.get("detail", {}).get("configuration", {}):
        for metric in alarm["detail"]["configuration"]["metrics"]:
            if 'label' in metric:
                alarm_name = metric["label"]

    # Instance info
    if 'instanceInfo' in alarm:
        if 'Error' not in alarm['instanceInfo']:
            for tag in alarm['instanceInfo'].get('Tags', []):
                if tag['Key'] == 'Name':
                    instance_name = tag['Value']
        else:
            resource_deleted_mark = '<b>*</b>'
            resource_strike_through = 'style="text-decoration:line-through;"'

    # Priority class
    priority = alarm.get('priority', 2)
    if priority == 1:
        priority_class = 'grid-item-prio'
    elif priority == 3:
        priority_class = 'grid-item-low'
    else:
        priority_class = 'grid-item'

    # Build detail popup HTML
    detail_html = build_alarm_detail_html(alarm, alarm_name, account_id, region, auxiliary_info)

    # Build grid item
    html = f'<div class="{priority_class}">'
    html += f'{safe_html(alarm_name)}<br />'
    html += f'<span {resource_strike_through}>{resource_deleted_mark}{safe_html(resource_id)}</span><br />'
    if instance_name:
        html += f'<span>{safe_html(instance_name)}</span><br />'
    html += f'{safe_html(account_id)} / {safe_html(region)}<br />'
    html += (f'<a class="btn btn-primary" style="background-color: rgba(255, 0, 0, 0.5); '
             f'width: 25px; padding: 5px; margin: 0; border: 1px solid black;">'
             f'{get_info_icon()}</a>'
             f'<cwdb-action action="html" display="popup" event="click">{detail_html}</cwdb-action>')
    html += '</div>\n'

    return html


def lambda_handler(event, context):
    """Render the alarm grid custom widget."""
    config = get_config()
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)

    query_params = {
        'IndexName': 'NonSuppressedAlarms',
        'KeyConditionExpression': 'stateValue = :stateVal AND suppressed = :suppressed',
        'ExpressionAttributeValues': {
            ':stateVal': 'ALARM',
            ':suppressed': 0
        }
    }

    alarms_in_alarm_state = []
    while True:
        response = table.query(**query_params)
        alarms_in_alarm_state.extend(response.get('Items', []))
        if 'LastEvaluatedKey' in response:
            query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
        else:
            break

    alarms_in_alarm_state = sort_by_priority(alarms_in_alarm_state)

    # Cap the number of alarms rendered to prevent timeout
    max_alarms = int(os.environ.get('MAX_GRID_ALARMS', MAX_GRID_ALARMS))
    total_alarms = len(alarms_in_alarm_state)
    capped = total_alarms > max_alarms
    alarms_to_render = alarms_in_alarm_state[:max_alarms]

    number_of_alarms = len(alarms_to_render)
    grid_size, font_size = get_grid_settings(number_of_alarms)

    # Count by priority
    critical_count = sum(1 for a in alarms_in_alarm_state if a.get('priority', 2) == 1)
    medium_count = sum(1 for a in alarms_in_alarm_state if a.get('priority', 2) == 2)
    low_count = sum(1 for a in alarms_in_alarm_state if a.get('priority', 2) == 3)

    # Build HTML
    body = '<!DOCTYPE html><html><head>'
    body += SHARED_CSS
    body += f'''
    <style>
        .grid-container {{
            display: grid;
            grid-template-columns: repeat({grid_size}, 1fr);
            grid-gap: 10px;
            padding: 0;
            margin: 0;
        }}
        .grid-item {{
            background-color: var(--medium-bg);
            border: 1px solid var(--medium-border);
            padding: 10px 4px 4px 4px;
            font-size: {font_size}px;
            text-align: center;
            text-overflow: ellipsis;
            overflow: hidden;
            white-space: nowrap;
        }}
        .grid-item-prio {{
            background-color: var(--critical-bg);
            border: 2px solid var(--critical-border);
            padding: 10px 4px 4px 4px;
            font-size: {font_size}px;
            text-align: center;
            text-overflow: ellipsis;
            overflow: hidden;
            white-space: nowrap;
        }}
        .grid-item-low {{
            background-color: var(--low-bg);
            border: 1px solid var(--low-border);
            padding: 10px 4px 4px 4px;
            font-size: {font_size}px;
            text-align: center;
            text-overflow: ellipsis;
            overflow: hidden;
            white-space: nowrap;
        }}
    </style>
    '''
    body += '</head><body>'

    # Summary bar
    body += '<div class="summary-bar">'
    body += f'<span class="count">{total_alarms} alarms in ALARM state</span>'
    if critical_count > 0:
        body += f'<span class="critical">{critical_count} Critical</span>'
    if medium_count > 0:
        body += f'<span class="medium">{medium_count} Medium</span>'
    if low_count > 0:
        body += f'<span class="low">{low_count} Low</span>'
    if capped:
        body += f'<span>(showing first {max_alarms})</span>'
    body += '</div>'

    # Empty state
    if total_alarms == 0:
        body += '<div class="empty-state">'
        body += '<p>No alarms currently in ALARM state.</p>'
        body += '<p style="font-size: 0.9rem; margin-top: 8px;">All monitored resources are healthy.</p>'
        body += '</div>'
    else:
        # Grid
        body += '<div class="grid-container">\n'
        for alarm in alarms_to_render:
            body += build_grid_item(alarm)
        body += '</div>'

    body += '</body></html>'
    return body
