"""
Alarm List Custom Widget Lambda
Renders a filterable, paginated table of all alarms with filtering,
sorting, suppression, and unsuppression capabilities.
"""

import os
import sys
import math
import json
from datetime import datetime

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import boto3
from boto3.dynamodb.conditions import Attr
from shared.utils import (
    get_config, get_alarm_type, safe_html, get_filter_icon,
    get_suppress_icon, get_unsuppress_icon, apply_filters_from_event,
    put_parameter_to_store, SHARED_CSS
)

dynamodb = boto3.resource('dynamodb')


def paginate_items(items, current_page, page_size):
    """Paginate a list of items. Returns the items for the current page."""
    if not items:
        return []

    pages = math.ceil(len(items) / page_size)

    if current_page < 1:
        current_page = 1
    if current_page > pages:
        current_page = pages

    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size
    return items[start_index:end_index]


def get_account_list(alarms):
    """Get sorted list of unique account IDs from alarms."""
    return sorted({alarm['alarmKey'].split('#')[0] for alarm in alarms})


def get_region_list(alarms):
    """Get sorted list of unique regions from alarms."""
    regions = set()
    for alarm in alarms:
        parts = alarm['alarmKey'].split('#')
        if len(parts) > 2:
            regions.add(parts[2])
    return sorted(regions)


def build_filter_popup(endpoint, filter_type, options):
    """Build a filter popup with options."""
    html = f'''<cwdb-action action="html" display="popup" event="click">
    <div class="filter-popup">'''
    for option in options:
        label = safe_html(str(option.get('label', option.get('value', ''))))
        value = option.get('value', '')
        html += f'''<a class="btn btn-primary">{label}</a>
        <cwdb-action action="call" confirmation="Apply filter: {label}"
            endpoint="{endpoint}">
            {{ "{filter_type}": "{value}" }}
        </cwdb-action>'''
    html += '</div></cwdb-action>'
    return html


def build_clear_filter_action(endpoint, filter_type):
    """Build a clear filter action (when filter is active)."""
    return f'''<cwdb-action action="call" confirmation="Remove this filter"
        endpoint="{endpoint}">
        {{ "{filter_type}": "none" }}
    </cwdb-action>'''


def build_pagination_html(current_page, total_pages, endpoint):
    """Build pagination UI with Previous/Next and ellipsis."""
    if total_pages <= 1:
        return ''

    html = '<div class="pagination">'

    # Previous button
    if current_page > 1:
        html += f'''<a>&laquo; Prev</a><cwdb-action action="call"
            endpoint="{endpoint}">
            {{ "currentAlarmViewPage": {current_page - 1} }}
        </cwdb-action>'''

    # Page numbers with ellipsis
    pages_to_show = set()
    pages_to_show.add(1)
    pages_to_show.add(total_pages)
    for p in range(max(1, current_page - 2), min(total_pages + 1, current_page + 3)):
        pages_to_show.add(p)

    prev_page = 0
    for p in sorted(pages_to_show):
        if p - prev_page > 1:
            html += '<span>...</span>'
        if p == current_page:
            html += f'<span class="current-page">{p}</span>'
        else:
            html += f'''<a>{p}</a><cwdb-action action="call"
                endpoint="{endpoint}">
                {{ "currentAlarmViewPage": {p} }}
            </cwdb-action>'''
        prev_page = p

    # Next button
    if current_page < total_pages:
        html += f'''<a>Next &raquo;</a><cwdb-action action="call"
            endpoint="{endpoint}">
            {{ "currentAlarmViewPage": {current_page + 1} }}
        </cwdb-action>'''

    html += '</div>'
    return html


def build_alarm_detail_popup(alarm, auxiliary_info, region):
    """Build the detail popup HTML for a single alarm row."""
    aux_html = ''

    # Alternate Contact
    if 'AlternateContact' in auxiliary_info and auxiliary_info['AlternateContact']:
        aux_html += "<hr /><h4>Alternate Contact (OPERATIONS)</h4><div>"
        contact = auxiliary_info['AlternateContact']
        if 'Name' in contact:
            aux_html += f'Name: {safe_html(contact["Name"])}<br />'
        if 'Title' in contact:
            aux_html += f'Title: {safe_html(contact["Title"])}<br />'
        if 'PhoneNumber' in contact:
            aux_html += f'Phone: {safe_html(contact["PhoneNumber"])}<br />'
        if 'EmailAddress' in contact:
            email = safe_html(contact["EmailAddress"])
            aux_html += f'Email: <a href="mailto:{email}">{email}</a>'
        aux_html += '</div>'

    # Account Info
    if 'Account' in auxiliary_info and auxiliary_info['Account']:
        aux_html += "<hr /><h4>Account Info</h4>"
        acct = auxiliary_info['Account']
        aux_html += f'<div>Id: {safe_html(acct.get("Id", ""))}</div>'
        if 'Status' in acct:
            aux_html += f'<div>Status: {safe_html(acct["Status"])}</div>'
        if 'Email' in acct:
            email = safe_html(acct["Email"])
            aux_html += f'<div>Email: <a href="mailto:{email}">{email}</a></div>'

    # Alarm Details
    aux_html += "<hr /><h4>Alarm Details</h4>"
    aux_html += f'<div>Name: {safe_html(alarm["detail"]["alarmName"])}</div>'
    aux_html += f'<div>State: {safe_html(alarm["detail"]["state"]["value"])}</div>'
    aux_html += f'<div>Timestamp: {safe_html(alarm["detail"]["state"]["timestamp"])}</div>'
    aux_html += f'<div>Reason: {safe_html(alarm["detail"]["state"]["reason"])}</div>'

    # Metric Info
    aux_html += '<hr /><h4>Metric Info</h4>'
    if "metrics" in alarm.get("detail", {}).get("configuration", {}):
        for metric in alarm["detail"]["configuration"]["metrics"]:
            if 'expression' in metric:
                aux_html += f'<div><b>Expression:</b> {safe_html(metric["expression"])}</div>'
                aux_html += f'<div><b>Label:</b> {safe_html(metric["label"])}</div>'
            if 'metricStat' in metric:
                aux_html += f'<div>Namespace: {safe_html(metric["metricStat"]["metric"]["namespace"])}</div>'
                aux_html += f'<div>Metric: {safe_html(metric["metricStat"]["metric"]["name"])}</div>'
                for dim_key, dim_val in metric["metricStat"]["metric"].get("dimensions", {}).items():
                    aux_html += f'<div>{safe_html(dim_key)}: {safe_html(dim_val)}</div>'
            aux_html += '<hr />'
    else:
        if "alarmRule" in alarm.get("detail", {}).get("configuration", {}):
            aux_html += f'<div>Alarm Rule: {safe_html(alarm["detail"]["configuration"]["alarmRule"])}</div>'
            aux_html += '<hr />'

    # Alarm Link (using actual region)
    alarm_name_encoded = safe_html(alarm["detail"]["alarmName"])
    aux_html += f'<hr /><h4>Alarm Link</h4>'
    aux_html += (f'<a href="https://{safe_html(region)}.console.aws.amazon.com/cloudwatch/'
                 f'home?region={safe_html(region)}#alarmsV2:alarm/{alarm_name_encoded}?">'
                 f'View in CloudWatch Console</a>')

    return aux_html


def lambda_handler(event, context):
    """Render the alarm list custom widget."""
    print(f'Event: {json.dumps(event, default=str)}')

    config = get_config(use_cache=False)  # Always fresh for filter state

    # Apply filters from event and only persist if something changed
    config, filters_changed = apply_filters_from_event(event, config)
    if filters_changed:
        param_name = os.environ.get('CONFIG_PARAMETER_NAME', 'CloudWatchAlarmWidgetConfigCDK')
        put_parameter_to_store(param_name, json.dumps(config))

    configurator_lambda_function = config.get(
        'configuratorLambdaFunction',
        os.environ.get('CONFIGURATOR_LAMBDA_ARN', '')
    )
    table_name = config.get('dynamoTableName', os.environ.get('DYNAMO_TABLE_NAME', 'AlarmStateChangeTableCDK'))
    table = dynamodb.Table(table_name)

    # Determine filter icon colors (red = active)
    region_filter_active = 'region_filter' in config and config['region_filter'] != "none"
    account_filter_active = 'account_filter' in config and config['account_filter'] != "none"
    state_filter_active = 'state_filter' in config and config['state_filter'] != "none"
    priority_filter_active = 'priority_filter' in config and config['priority_filter'] != "none"

    region_icon_color = "ff0000" if region_filter_active else "000000"
    account_icon_color = "ff0000" if account_filter_active else "000000"
    state_icon_color = "ff0000" if state_filter_active else "000000"
    priority_icon_color = "ff0000" if priority_filter_active else "000000"

    any_filter_active = region_filter_active or account_filter_active or state_filter_active or priority_filter_active

    # Build DynamoDB filter expressions
    filter_expressions = []
    if region_filter_active:
        filter_expressions.append(Attr("alarmKey").contains("#" + config['region_filter']))
    if account_filter_active:
        filter_expressions.append(Attr("alarmKey").begins_with(config['account_filter'] + "#"))
    if state_filter_active:
        filter_expressions.append(Attr("stateValue").eq(config['state_filter']))
    if priority_filter_active:
        filter_expressions.append(Attr("priority").eq(int(config['priority_filter'])))

    query_params = {
        'IndexName': 'SuppressionIndex',
        'KeyConditionExpression': 'suppressed = :suppressed',
        'ExpressionAttributeValues': {':suppressed': 0},
        'ReturnConsumedCapacity': 'TOTAL'
    }

    if filter_expressions:
        combined = filter_expressions[0]
        for expr in filter_expressions[1:]:
            combined &= expr
        query_params['FilterExpression'] = combined

    # Fetch all matching alarms
    alarms = []
    consumed_rrus = 0
    while True:
        response = table.query(**query_params)
        alarms.extend(response.get('Items', []))
        if 'ConsumedCapacity' in response:
            consumed_rrus += response['ConsumedCapacity']['CapacityUnits']
        if 'LastEvaluatedKey' in response:
            query_params['ExclusiveStartKey'] = response['LastEvaluatedKey']
        else:
            break

    # Cost estimation
    monthly_executions = 6 * 60 * 24 * 30  # 10-second refresh, 24/7
    total_monthly_rrus = consumed_rrus * monthly_executions
    total_monthly_cost = round(total_monthly_rrus * (0.283 / 1000000), 2)
    est_monthly_cost = round(total_monthly_cost * 1.75, 2)

    # Pagination
    page = int(config.get('currentAlarmViewPage', 1))
    if page == "none" or not page:
        page = 1
    page_size = int(config.get('alarmViewListSize', 100))
    total_filtered_pages = max(1, math.ceil(len(alarms) / page_size))
    paginated_alarms = paginate_items(alarms, page, page_size)

    endpoint = context.invoked_function_arn

    # Build HTML
    html = SHARED_CSS
    html += '<div style="width:100%;">'

    # Clear all filters button
    if any_filter_active:
        html += f'''<div style="margin-bottom: 8px;">
            <a class="btn btn-primary" style="background-color: #f44336; color: white; padding: 4px 12px; border-radius: 3px;">
            Clear All Filters</a>
            <cwdb-action action="call" confirmation="Remove all active filters?"
                endpoint="{endpoint}">
                {{ "region": "none", "account": "none", "state": "none", "priority": "none" }}
            </cwdb-action>
        </div>'''

    # Pagination
    html += build_pagination_html(page, total_filtered_pages, endpoint)

    # Empty state
    if not alarms:
        html += '<div class="empty-state">'
        html += '<p>No alarms match the current filters.</p>'
        if any_filter_active:
            html += '<p style="font-size: 0.9rem; margin-top: 8px;">Try clearing some filters.</p>'
        html += '</div>'
        html += '</div>'
        return html

    # Table header
    html += '<table style="width:100%;">'
    html += '<thead><tr>'

    # State column header with filter
    html += f'<th>Alarm State <a>{get_filter_icon(state_icon_color)}</a>'
    if not state_filter_active:
        html += build_filter_popup(endpoint, 'state', [
            {'label': 'OK', 'value': 'OK'},
            {'label': 'ALARM', 'value': 'ALARM'},
            {'label': 'INSUFFICIENT_DATA', 'value': 'INSUFFICIENT_DATA'}
        ])
    else:
        html += build_clear_filter_action(endpoint, 'state')
    html += '</th>'

    # Priority column header with filter
    html += f'<th>Priority <a>{get_filter_icon(priority_icon_color)}</a>'
    if not priority_filter_active:
        html += build_filter_popup(endpoint, 'priority', [
            {'label': 'CRITICAL', 'value': '1'},
            {'label': 'Medium', 'value': '2'},
            {'label': 'Low', 'value': '3'}
        ])
    else:
        html += build_clear_filter_action(endpoint, 'priority')
    html += '</th>'

    html += '<th>Alarm Name</th>'
    html += '<th>Alarm Updated</th>'

    # Account column header with filter
    html += f'<th>Account <a>{get_filter_icon(account_icon_color)}</a>'
    if not account_filter_active:
        account_options = [{'label': acc, 'value': acc} for acc in get_account_list(alarms)]
        html += build_filter_popup(endpoint, 'account', account_options)
    else:
        html += build_clear_filter_action(endpoint, 'account')
    html += '</th>'

    # Region column header with filter
    html += f'<th>Region <a>{get_filter_icon(region_icon_color)}</a>'
    if not region_filter_active:
        region_options = [{'label': r, 'value': r} for r in get_region_list(alarms)]
        html += build_filter_popup(endpoint, 'region', region_options)
    else:
        html += build_clear_filter_action(endpoint, 'region')
    html += '</th>'

    html += '<th>Contact Email</th>'
    html += '<th>Operations Contact</th>'

    # Cost column header with popup
    html += (f'<th><a>Cost</a><cwdb-action action="html" event="click" display="popup">'
             f'Estimated cost: <b>${est_monthly_cost}/mo</b><br /><br />'
             f'<div style="background-color: var(--bg-secondary); padding: 10px; font-size: 12px;">'
             f'Based on {consumed_rrus} RRUs per request, '
             f'{monthly_executions} monthly executions (10s refresh 24/7).<br />'
             f'Formula: base_cost * 1.75 (includes write + alarm-view overhead estimate).<br /><br />'
             f'Verify actual cost using AWS Cost Explorer.'
             f'</div></cwdb-action></th>')

    html += '</tr></thead>'

    # Table body
    for alarm in paginated_alarms:
        html += '<tr>'

        account_id = alarm['alarmKey'].split('#')[0]
        alarm_name = alarm['alarmKey'].split('#')[1]
        try:
            region = alarm['alarmKey'].split('#')[2]
        except IndexError:
            region = 'unknown'

        auxiliary_info = alarm.get('auxiliaryInfo', {})

        # State column
        state_value = alarm.get("detail", {}).get("state", {}).get("value", "UNKNOWN")
        if state_value == "ALARM":
            color = "var(--alarm-text)"
            status_label = "ALARM"
        elif state_value == "OK":
            color = "var(--ok-color)"
            status_label = "OK"
        else:
            color = "var(--text-secondary)"
            status_label = "INS_DAT"

        html += f'''<td style="color:{color}"><a style="color:{color}">{status_label}</a>
            <cwdb-action action="call" confirmation="Apply filter: {status_label}"
                endpoint="{endpoint}">
                {{ "state": "{state_value}" }}
            </cwdb-action></td>'''

        # Priority column
        priority = alarm.get('priority', 2)
        priority_names = {1: 'CRITICAL', 2: 'Medium', 3: 'Low'}
        priority_name = priority_names.get(priority, 'Not set')
        html += f'''<td><a>{priority_name}</a>
            <cwdb-action action="call" confirmation="Apply filter: {priority_name}"
                endpoint="{endpoint}">
                {{ "priority": "{priority}" }}
            </cwdb-action></td>'''

        # Alarm Name column with suppress/unsuppress
        html += f'''<td><a>{get_suppress_icon()}</a>
            <cwdb-action action="call" confirmation="WARNING: This will SUPPRESS this alarm from the dashboard"
                display="popup" endpoint="{configurator_lambda_function}">
                {{ "suppress": "{safe_html(alarm['alarmKey'])}" }}
            </cwdb-action> {safe_html(alarm["detail"]["alarmName"])}</td>'''

        # Timestamp column
        try:
            timestamp = alarm["detail"]["state"]["timestamp"].replace("+0000", "")
            timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%f").strftime("%m/%d/%Y %H:%M:%S")
        except (ValueError, KeyError):
            timestamp = 'N/A'
        html += f'<td style="font-size: 0.8rem;">{safe_html(timestamp)}</td>'

        # Account column
        html += f'''<td><a>{safe_html(account_id)}</a>
            <cwdb-action action="call" confirmation="Apply filter: {safe_html(account_id)}"
                endpoint="{endpoint}">
                {{ "account": "{safe_html(account_id)}" }}
            </cwdb-action></td>'''

        # Region column
        html += f'''<td style="width: 10%;"><a>{safe_html(region)}</a>
            <cwdb-action action="call" confirmation="Apply filter: {safe_html(region)}"
                endpoint="{endpoint}">
                {{ "region": "{safe_html(region)}" }}
            </cwdb-action></td>'''

        # Contact email column
        email = ''
        if 'Account' in auxiliary_info and 'Email' in auxiliary_info['Account']:
            email = safe_html(auxiliary_info["Account"]["Email"])
        html += f'<td>{email}</td>'

        # Operations contact column
        html += '<td>'
        if 'AlternateContact' in auxiliary_info and auxiliary_info['AlternateContact']:
            contact = auxiliary_info['AlternateContact']
            if 'EmailAddress' in contact:
                email = safe_html(contact["EmailAddress"])
                html += f'<b><a href="mailto:{email}">{email}</a></b><br />'
            if 'PhoneNumber' in contact:
                phone = safe_html(contact["PhoneNumber"])
                html += f'<b><a href="tel:{phone}">{phone}</a></b>'
        html += '</td>'

        # More details column
        aux_html = build_alarm_detail_popup(alarm, auxiliary_info, region)
        html += (f'<td><a class="btn" style="font-size:0.6rem; font-weight:400;">More</a>'
                 f'<cwdb-action action="html" display="popup" event="click">'
                 f'{aux_html}</cwdb-action></td>')

        html += '</tr>'

    html += '</table>'

    # Bottom pagination
    html += build_pagination_html(page, total_filtered_pages, endpoint)
    html += '</div>'

    return html
