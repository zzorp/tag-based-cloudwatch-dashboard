"""
Shared utility functions for alarm dashboard Lambda functions.
Contains common helpers used across alarm_view, alarm_list, and configuration_handler.
"""

import json
import os
import re
import time
import boto3
from html import escape as html_escape

ssm_client = boto3.client('ssm')

# Module-level SSM config cache
_config_cache = (None, 0)
CONFIG_CACHE_TTL = 60  # seconds


def get_parameter_from_store(param_name):
    """Retrieve a parameter from SSM Parameter Store."""
    response = ssm_client.get_parameter(
        Name=param_name,
        WithDecryption=True
    )
    return response['Parameter']['Value']


def put_parameter_to_store(param_name, param_value):
    """Write a parameter to SSM Parameter Store."""
    response = ssm_client.put_parameter(
        Name=param_name,
        Value=param_value,
        Type='String',
        Overwrite=True
    )
    return response


def get_config(use_cache=True):
    """
    Get config, using environment variables for static values
    and SSM for mutable filter state.
    """
    global _config_cache

    now = time.time()
    if use_cache and _config_cache[0] is not None and (now - _config_cache[1]) < CONFIG_CACHE_TTL:
        return _config_cache[0]

    param_name = os.environ.get('CONFIG_PARAMETER_NAME', 'CloudWatchAlarmWidgetConfigCDK')
    config = json.loads(get_parameter_from_store(param_name))

    # Override with env vars if available (static config)
    if os.environ.get('DYNAMO_TABLE_NAME'):
        config['dynamoTableName'] = os.environ['DYNAMO_TABLE_NAME']
    if os.environ.get('CONFIGURATOR_LAMBDA_ARN'):
        config['configuratorLambdaFunction'] = os.environ['CONFIGURATOR_LAMBDA_ARN']

    _config_cache = (config, now)
    return config


def is_expression_alarm(alarm):
    """Check if alarm uses metric math expressions."""
    if "metrics" not in alarm.get("detail", {}).get("configuration", {}):
        return False
    for metric in alarm["detail"]["configuration"]["metrics"]:
        if 'expression' in metric:
            return True
    return False


def get_alarm_type(alarm):
    """Determine alarm type: composite, expression, or standard."""
    if "metrics" not in alarm.get("detail", {}).get("configuration", {}):
        return "composite"
    elif is_expression_alarm(alarm):
        return "expression"
    else:
        return "standard"


def safe_html(value):
    """HTML-escape a value to prevent XSS attacks."""
    if value is None:
        return ''
    return html_escape(str(value), quote=True)


def sanitize_filter_value(value, allowed_pattern=None):
    """
    Sanitize a filter value before storing in SSM.
    Rejects values that don't match expected patterns.
    """
    if value is None:
        return "none"

    value = str(value).strip()

    # Reject excessively long values
    if len(value) > 256:
        return "none"

    # If a specific pattern is provided, validate against it
    if allowed_pattern and not re.match(allowed_pattern, value):
        return "none"

    return value


def validate_region(region):
    """Validate an AWS region string."""
    pattern = r'^[a-z]{2}-[a-z]+-\d+$'
    if re.match(pattern, region):
        return region
    return "none"


def validate_account_id(account_id):
    """Validate an AWS account ID."""
    pattern = r'^\d{12}$'
    if re.match(pattern, account_id):
        return account_id
    return "none"


def validate_state(state):
    """Validate an alarm state value."""
    valid_states = ('OK', 'ALARM', 'INSUFFICIENT_DATA', 'none')
    if state in valid_states:
        return state
    return "none"


def validate_priority(priority):
    """Validate a priority value."""
    try:
        p = int(priority)
        if p in (1, 2, 3):
            return p
    except (ValueError, TypeError):
        pass
    return "none"


def apply_filters_from_event(event, config):
    """
    Apply filter parameters from an event to the config.
    Returns (config, changed) where changed indicates if any filter was modified.
    """
    changed = False

    if 'region' in event:
        new_val = validate_region(event['region']) if event['region'] != 'none' else 'none'
        if config.get('region_filter') != new_val:
            config['region_filter'] = new_val
            changed = True

    if 'sort_by_region' in event:
        new_val = sanitize_filter_value(event['sort_by_region'])
        if config.get('sort_by_region') != new_val:
            config['sort_by_region'] = new_val
            changed = True

    if 'account' in event:
        new_val = validate_account_id(event['account']) if event['account'] != 'none' else 'none'
        if config.get('account_filter') != new_val:
            config['account_filter'] = new_val
            changed = True

    if 'sort_by_account' in event:
        new_val = sanitize_filter_value(event['sort_by_account'])
        if config.get('sort_by_account') != new_val:
            config['sort_by_account'] = new_val
            changed = True

    if 'state' in event:
        new_val = validate_state(event['state'])
        if config.get('state_filter') != new_val:
            config['state_filter'] = new_val
            changed = True

    if 'priority' in event:
        new_val = validate_priority(event['priority']) if event['priority'] != 'none' else 'none'
        if config.get('priority_filter') != new_val:
            config['priority_filter'] = new_val
            changed = True

    if 'currentAlarmViewPage' in event:
        try:
            new_val = int(event['currentAlarmViewPage'])
            if config.get('currentAlarmViewPage') != new_val:
                config['currentAlarmViewPage'] = new_val
                changed = True
        except (ValueError, TypeError):
            pass

    return config, changed


# SVG Icon constants
FILTER_ICON_SVG = '''<svg fill="#{color}" height="12px" width="12px" version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300.906 300.906"><g><path d="M288.953,0h-277c-5.522,0-10,4.478-10,10v49.531c0,5.522,4.478,10,10,10h12.372l91.378,107.397v113.978c0,3.688,2.03,7.076,5.281,8.816c1.479,0.792,3.101,1.184,4.718,1.184c1.94,0,3.875-0.564,5.548-1.68l49.5-33c2.782-1.854,4.453-4.977,4.453-8.32v-80.978l91.378-107.397h12.372c5.522,0,10-4.478,10-10V10C298.953,4.478,294.476,0,288.953,0z M167.587,166.77c-1.539,1.809-2.384,4.105-2.384,6.48v79.305l-29.5,19.666V173.25c0-2.375-0.845-4.672-2.384-6.48L50.585,69.531h199.736L167.587,166.77z M278.953,49.531h-257V20h257V49.531z"/></g></svg>'''

SUPPRESS_ICON_SVG = '''<svg fill="#9a9898" height="12px" width="12px" version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 27.965 27.965"><g><path d="M13.98,0C6.259,0,0,6.261,0,13.983c0,7.721,6.259,13.982,13.98,13.982c7.725,0,13.985-6.262,13.985-13.982C27.965,6.261,21.705,0,13.98,0z M19.992,17.769l-2.227,2.224c0,0-3.523-3.78-3.786-3.78c-0.259,0-3.783,3.78-3.783,3.78l-2.228-2.224c0,0,3.784-3.472,3.784-3.781c0-0.314-3.784-3.787-3.784-3.787l2.228-2.229c0,0,3.553,3.782,3.783,3.782c0.232,0,3.786-3.782,3.786-3.782l2.227,2.229c0,0-3.785,3.523-3.785,3.787C16.207,14.239,19.992,17.769,19.992,17.769z"/></g></svg>'''

UNSUPPRESS_ICON_SVG = '''<svg fill="#4CAF50" height="12px" width="12px" version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 27.965 27.965"><g><path d="M13.98,0C6.259,0,0,6.261,0,13.983c0,7.721,6.259,13.982,13.98,13.982c7.725,0,13.985-6.262,13.985-13.982C27.965,6.261,21.705,0,13.98,0z M21.5,11.5l-8.5,8.5l-5.5-5.5l2-2l3.5,3.5l6.5-6.5L21.5,11.5z"/></g></svg>'''

INFO_ICON_SVG = '''<svg fill="#ffffff" version="1.1" xmlns="http://www.w3.org/2000/svg" width="10px" height="10px" viewBox="0 0 416.979 416.979"><g><path d="M356.004,61.156c-81.37-81.47-213.377-81.551-294.848-0.182c-81.47,81.371-81.552,213.379-0.181,294.85c81.369,81.47,213.378,81.551,294.849,0.181C437.293,274.636,437.375,142.626,356.004,61.156z M237.6,340.786c0,3.217-2.607,5.822-5.822,5.822h-46.576c-3.215,0-5.822-2.605-5.822-5.822V167.885c0-3.217,2.607-5.822,5.822-5.822h46.576c3.215,0,5.822,2.604,5.822,5.822V340.786z M208.49,137.901c-18.618,0-33.766-15.146-33.766-33.765c0-18.617,15.147-33.766,33.766-33.766c18.619,0,33.766,15.148,33.766,33.766C242.256,122.755,227.107,137.901,208.49,137.901z"/></g></svg>'''


def get_filter_icon(color_code):
    """Return filter icon SVG with the specified color."""
    return FILTER_ICON_SVG.replace('{color}', color_code)


def get_suppress_icon():
    """Return suppress (X) icon SVG."""
    return SUPPRESS_ICON_SVG


def get_unsuppress_icon():
    """Return unsuppress (checkmark) icon SVG."""
    return UNSUPPRESS_ICON_SVG


def get_info_icon():
    """Return info icon SVG."""
    return INFO_ICON_SVG


# Shared CSS with dark mode support
SHARED_CSS = '''
<style>
    :root {
        --bg-primary: #ffffff;
        --bg-secondary: #f5f5f5;
        --text-primary: #333333;
        --text-secondary: #666666;
        --border-color: rgba(0, 0, 0, 0.12);
        --alarm-color: #ff4c30;
        --critical-bg: rgba(255, 0, 0, 0.2);
        --critical-border: rgba(255, 0, 0, 1);
        --medium-bg: rgba(255, 255, 255, 0.8);
        --medium-border: rgba(255, 76, 48, 0.8);
        --low-bg: rgba(0, 0, 0, 0.1);
        --low-border: rgba(0, 0, 0, 0.8);
        --ok-color: #4CAF50;
        --alarm-text: #f44336;
        --shadow-sm: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        --shadow-lg: 0 14px 28px rgba(0,0,0,0.25), 0 10px 10px rgba(0,0,0,0.22);
    }

    @media (prefers-color-scheme: dark) {
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --text-primary: #e0e0e0;
            --text-secondary: #b0b0b0;
            --border-color: rgba(255, 255, 255, 0.12);
            --critical-bg: rgba(255, 0, 0, 0.3);
            --critical-border: rgba(255, 80, 80, 1);
            --medium-bg: rgba(255, 255, 255, 0.1);
            --medium-border: rgba(255, 120, 80, 0.8);
            --low-bg: rgba(255, 255, 255, 0.05);
            --low-border: rgba(255, 255, 255, 0.3);
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.4);
            --shadow-lg: 0 14px 28px rgba(0,0,0,0.5), 0 10px 10px rgba(0,0,0,0.4);
        }
    }

    * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }

    body {
        color: var(--text-primary);
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    .btn-primary {
        display: inline-block;
        padding: 6px 12px;
        margin: 4px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.85rem;
    }

    .card {
        background: var(--bg-primary);
        border-radius: 4px;
        display: inline-block;
        margin: 1rem;
        position: relative;
        box-shadow: var(--shadow-sm);
        transition: all 0.3s cubic-bezier(.25,.8,.25,1);
    }

    .card:hover {
        box-shadow: var(--shadow-lg);
    }

    .card-content {
        padding: 16px;
    }

    .card-content h4 {
        margin-top: 0;
        font-size: 1.3em;
        color: var(--text-primary);
    }

    .card-content div {
        margin-bottom: 8px;
        color: var(--text-secondary);
    }

    .summary-bar {
        display: flex;
        gap: 16px;
        padding: 8px 12px;
        background: var(--bg-secondary);
        border-radius: 4px;
        margin-bottom: 10px;
        font-size: 0.9rem;
        align-items: center;
    }

    .summary-bar .count {
        font-weight: bold;
        font-size: 1.1rem;
    }

    .summary-bar .critical { color: var(--critical-border); }
    .summary-bar .medium { color: var(--alarm-color); }
    .summary-bar .low { color: var(--text-secondary); }

    .filter-popup {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        padding: 16px;
    }

    .filter-popup a {
        margin: 8px;
    }

    .pagination {
        display: flex;
        gap: 4px;
        align-items: center;
        padding: 8px 0;
        flex-wrap: wrap;
    }

    .pagination a, .pagination span {
        padding: 4px 8px;
        border-radius: 3px;
    }

    .pagination .current-page {
        font-weight: bold;
        background: var(--bg-secondary);
    }

    .empty-state {
        text-align: center;
        padding: 40px 20px;
        color: var(--text-secondary);
        font-size: 1.1rem;
    }

    .empty-state svg {
        margin-bottom: 12px;
    }
</style>
'''
