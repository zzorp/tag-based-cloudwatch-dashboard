"""Alarm List Custom Widget - filterable paginated table of all alarms."""
import os
import sys
import math
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from boto3.dynamodb.conditions import Attr
from shared.utils import (
    get_config, get_alarm_type, safe_html, get_filter_icon,
    get_suppress_icon, apply_filters_from_event, put_parameter_to_store,
)

dynamodb = boto3.resource('dynamodb')


def paginate_items(items, current_page, page_size):
    if not items:
        return []
    pages = math.ceil(len(items) / page_size)
    if current_page < 1:
        current_page = 1
    if current_page > pages:
        current_page = pages
    start = (current_page - 1) * page_size
    return items[start:start + page_size]


def get_account_list(alarms):
    return sorted({a['alarmKey'].split('#')[0] for a in alarms})


def get_region_list(alarms):
    regions = set()
    for a in alarms:
        parts = a['alarmKey'].split('#')
        if len(parts) > 2:
            regions.add(parts[2])
    return sorted(regions)


def build_filter_popup(endpoint, filter_type, options):
    html = '<cwdb-action action="html" display="popup" event="click"><div style="padding:16px;">'
    for opt in options:
        label = safe_html(str(opt.get('label', opt.get('value', ''))))
        value = opt.get('value', '')
        html += (f'<a class="btn btn-primary" style="margin:4px;">{label}</a>'
                 f'<cwdb-action action="call" confirmation="Apply filter: {label}"'
                 f' endpoint="{endpoint}">{{ "{filter_type}": "{value}" }}</cwdb-action>')
    html += '</div></cwdb-action>'
    return html


def build_pagination_html(current_page, total_pages, endpoint):
    if total_pages <= 1:
        return ''
    html = '<div style="padding:8px 0;">'
    if current_page > 1:
        html += f'<a>Prev</a><cwdb-action action="call" endpoint="{endpoint}">{{ "currentAlarmViewPage": {current_page - 1} }}</cwdb-action> '
    for p in range(1, total_pages + 1):
        if abs(p - current_page) <= 2 or p == 1 or p == total_pages:
            if p == current_page:
                html += f'<b>{p}</b> '
            else:
                html += f'<a>{p}</a><cwdb-action action="call" endpoint="{endpoint}">{{ "currentAlarmViewPage": {p} }}</cwdb-action> '
        elif abs(p - current_page) == 3:
            html += '... '
    if current_page < total_pages:
        html += f'<a>Next</a><cwdb-action action="call" endpoint="{endpoint}">{{ "currentAlarmViewPage": {current_page + 1} }}</cwdb-action>'
    html += '</div>'
    return html


def lambda_handler(event, context):
    config = get_config(use_cache=False)
    config, filters_changed = apply_filters_from_event(event, config)

    if filters_changed:
        param_name = os.environ.get('CONFIG_PARAMETER_NAME', 'CloudWatchAlarmWidgetConfigCDK')
        put_parameter_to_store(param_name, json.dumps(config))

    configurator = config.get('configuratorLambdaFunction', os.environ.get('CONFIGURATOR_LAMBDA_ARN', ''))
    table = dynamodb.Table(config['dynamoTableName'])
    endpoint = context.invoked_function_arn

    # Filter state
    region_active = config.get('region_filter', 'none') != 'none' and 'region_filter' in config
    account_active = config.get('account_filter', 'none') != 'none' and 'account_filter' in config
    state_active = config.get('state_filter', 'none') != 'none' and 'state_filter' in config
    priority_active = config.get('priority_filter', 'none') != 'none' and 'priority_filter' in config
    any_active = region_active or account_active or state_active or priority_active

    # Build DynamoDB filters
    filter_expressions = []
    if region_active:
        filter_expressions.append(Attr("alarmKey").contains("#" + config['region_filter']))
    if account_active:
        filter_expressions.append(Attr("alarmKey").begins_with(config['account_filter'] + "#"))
    if state_active:
        filter_expressions.append(Attr("stateValue").eq(config['state_filter']))
    if priority_active:
        filter_expressions.append(Attr("priority").eq(int(config['priority_filter'])))

    query_params = {
        'IndexName': 'SuppressionIndex',
        'KeyConditionExpression': 'suppressed = :suppressed',
        'ExpressionAttributeValues': {':suppressed': 0},
    }
    if filter_expressions:
        combined = filter_expressions[0]
        for expr in filter_expressions[1:]:
            combined &= expr
        query_params['FilterExpression'] = combined

    alarms = []
    while True:
        response = table.query(**query_params)
        alarms.extend(response.get('Items', []))
        if 'LastEvaluatedKey' in response:
            query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
        else:
            break

    # Pagination
    page = int(config.get('currentAlarmViewPage', 1) or 1)
    page_size = int(config.get('alarmViewListSize', 100) or 100)
    total_pages = max(1, math.ceil(len(alarms) / page_size))
    paginated = paginate_items(alarms, page, page_size)

    # Build HTML
    html = ''

    # Clear all filters
    if any_active:
        html += (f'<div style="margin-bottom:8px;"><a style="background:#f44336;color:white;padding:4px 12px;'
                 f'border-radius:3px;">Clear All Filters</a>'
                 f'<cwdb-action action="call" confirmation="Remove all filters?"'
                 f' endpoint="{endpoint}">'
                 f'{{ "region": "none", "account": "none", "state": "none", "priority": "none" }}'
                 f'</cwdb-action></div>')

    html += build_pagination_html(page, total_pages, endpoint)

    if not alarms:
        html += '<div style="text-align:center;padding:40px;color:#666;">No alarms match current filters.</div>'
        return html

    # Table header
    ri, ai, si, pi = ("ff0000" if region_active else "000000", "ff0000" if account_active else "000000",
                       "ff0000" if state_active else "000000", "ff0000" if priority_active else "000000")

    html += '<table style="width:100%;"><thead><tr>'
    html += f'<th>State <a>{get_filter_icon(si)}</a>'
    if not state_active:
        html += build_filter_popup(endpoint, 'state', [{'label': 'OK', 'value': 'OK'}, {'label': 'ALARM', 'value': 'ALARM'}, {'label': 'INSUFFICIENT_DATA', 'value': 'INSUFFICIENT_DATA'}])
    else:
        html += f'<cwdb-action action="call" confirmation="Remove filter" endpoint="{endpoint}">{{ "state": "none" }}</cwdb-action>'
    html += '</th>'

    html += f'<th>Priority <a>{get_filter_icon(pi)}</a>'
    if not priority_active:
        html += build_filter_popup(endpoint, 'priority', [{'label': 'CRITICAL', 'value': '1'}, {'label': 'Medium', 'value': '2'}, {'label': 'Low', 'value': '3'}])
    else:
        html += f'<cwdb-action action="call" confirmation="Remove filter" endpoint="{endpoint}">{{ "priority": "none" }}</cwdb-action>'
    html += '</th>'

    html += '<th>Alarm Name</th><th>Updated</th>'

    html += f'<th>Account <a>{get_filter_icon(ai)}</a>'
    if not account_active:
        html += build_filter_popup(endpoint, 'account', [{'label': a, 'value': a} for a in get_account_list(alarms)])
    else:
        html += f'<cwdb-action action="call" confirmation="Remove filter" endpoint="{endpoint}">{{ "account": "none" }}</cwdb-action>'
    html += '</th>'

    html += f'<th>Region <a>{get_filter_icon(ri)}</a>'
    if not region_active:
        html += build_filter_popup(endpoint, 'region', [{'label': r, 'value': r} for r in get_region_list(alarms)])
    else:
        html += f'<cwdb-action action="call" confirmation="Remove filter" endpoint="{endpoint}">{{ "region": "none" }}</cwdb-action>'
    html += '</th>'
    html += '<th>Contact</th></tr></thead>'

    # Table rows
    for alarm in paginated:
        account_id = alarm['alarmKey'].split('#')[0]
        try:
            region = alarm['alarmKey'].split('#')[2]
        except IndexError:
            region = 'unknown'

        state_val = alarm.get("detail", {}).get("state", {}).get("value", "UNKNOWN")
        color = "red" if state_val == "ALARM" else "green" if state_val == "OK" else "gray"

        priority = alarm.get('priority', 2)
        pname = {1: 'CRITICAL', 2: 'Medium', 3: 'Low'}.get(priority, 'N/A')

        try:
            ts = alarm["detail"]["state"]["timestamp"].replace("+0000", "")
            ts = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f").strftime("%m/%d/%Y %H:%M:%S")
        except (ValueError, KeyError):
            ts = 'N/A'

        aux = alarm.get('auxiliaryInfo', {})
        email = aux.get('Account', {}).get('Email', '')

        html += '<tr>'
        html += f'<td style="color:{color}">{state_val}</td>'
        html += f'<td>{pname}</td>'
        html += f'<td><a>{get_suppress_icon()}</a><cwdb-action action="call" confirmation="SUPPRESS this alarm" endpoint="{configurator}">{{ "suppress": "{safe_html(alarm["alarmKey"])}" }}</cwdb-action> {safe_html(alarm["detail"]["alarmName"])}</td>'
        html += f'<td style="font-size:0.8rem;">{safe_html(ts)}</td>'
        html += f'<td>{safe_html(account_id)}</td>'
        html += f'<td>{safe_html(region)}</td>'
        html += f'<td>{safe_html(email)}</td>'
        html += '</tr>'

    html += '</table>'
    html += build_pagination_html(page, total_pages, endpoint)
    return html
