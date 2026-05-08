"""Alarm View Custom Widget - renders a grid of alarms in ALARM state."""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from shared.utils import get_config, get_alarm_type, safe_html

dynamodb = boto3.resource('dynamodb')
MAX_GRID_ALARMS = 200


def sort_by_priority(alarms):
    for alarm in alarms:
        if 'priority' not in alarm:
            alarm['priority'] = 2
    return sorted(alarms, key=lambda x: x['priority'])


def lambda_handler(event, context):
    config = get_config()
    table = dynamodb.Table(config['dynamoTableName'])

    query_params = {
        'IndexName': 'NonSuppressedAlarms',
        'KeyConditionExpression': 'stateValue = :stateVal AND suppressed = :suppressed',
        'ExpressionAttributeValues': {':stateVal': 'ALARM', ':suppressed': 0},
    }

    alarms = []
    while True:
        response = table.query(**query_params)
        alarms.extend(response.get('Items', []))
        if 'LastEvaluatedKey' in response:
            query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
        else:
            break

    alarms = sort_by_priority(alarms)
    total = len(alarms)
    alarms = alarms[:MAX_GRID_ALARMS]
    num = len(alarms)

    grid_size, font_size = (10, 12) if num <= 30 else (15, 10) if num <= 60 else (20, 9) if num <= 80 else (25, 8)

    # Summary
    critical = sum(1 for a in alarms if a.get('priority', 2) == 1)
    medium = sum(1 for a in alarms if a.get('priority', 2) == 2)
    low = sum(1 for a in alarms if a.get('priority', 2) == 3)

    body = f'''<div style="padding:8px;background:#f5f5f5;margin-bottom:10px;border-radius:4px;">
    <b>{total} alarms in ALARM state</b>
    {f' | <span style="color:red">{critical} Critical</span>' if critical else ''}
    {f' | <span style="color:orange">{medium} Medium</span>' if medium else ''}
    {f' | <span style="color:gray">{low} Low</span>' if low else ''}
    </div>'''

    if total == 0:
        body += '<div style="text-align:center;padding:40px;color:#666;">No alarms currently in ALARM state.</div>'
        return body

    body += f'<div style="display:grid;grid-template-columns:repeat({grid_size},1fr);grid-gap:10px;">'

    for alarm in alarms:
        alarm_name = alarm['alarmKey'].split('#')[1]
        account_id = alarm['alarmKey'].split('#')[0]
        parts = alarm['alarmKey'].split('#')
        region = parts[2] if len(parts) > 2 else 'unknown'

        priority = alarm.get('priority', 2)
        if priority == 1:
            css = 'background:rgba(255,0,0,0.2);border:2px solid red;'
        elif priority == 3:
            css = 'background:rgba(0,0,0,0.05);border:1px solid #888;'
        else:
            css = 'background:rgba(255,255,255,0.8);border:1px solid rgba(255,76,48,0.8);'

        # Build detail popup
        detail = f'<h4>{safe_html(alarm["detail"]["alarmName"])}</h4>'
        detail += f'<div>Account: {safe_html(account_id)}</div>'
        detail += f'<div>Region: {safe_html(region)}</div>'
        detail += f'<div>State: {safe_html(alarm["detail"]["state"]["value"])}</div>'
        detail += f'<div>Reason: {safe_html(alarm["detail"]["state"]["reason"])}</div>'
        detail += f'<hr/><a href="https://{safe_html(region)}.console.aws.amazon.com/cloudwatch/home?region={safe_html(region)}#alarmsV2:alarm/{safe_html(alarm["detail"]["alarmName"])}?">View in Console</a>'

        body += (f'<div style="{css}padding:8px 4px;font-size:{font_size}px;text-align:center;'
                 f'overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">'
                 f'{safe_html(alarm_name)}<br/>{safe_html(account_id)}<br/>{safe_html(region)}'
                 f'<br/><a style="font-size:10px;">info</a>'
                 f'<cwdb-action action="html" display="popup" event="click">{detail}</cwdb-action>'
                 f'</div>')

    body += '</div>'
    return body
