"""
Shared utility functions for alarm dashboard Lambda functions.
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
CONFIG_CACHE_TTL = 60


def get_parameter_from_store(param_name):
    """Retrieve a parameter from SSM Parameter Store."""
    response = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
    return response['Parameter']['Value']


def put_parameter_to_store(param_name, param_value):
    """Write a parameter to SSM Parameter Store."""
    return ssm_client.put_parameter(
        Name=param_name, Value=param_value, Type='String', Overwrite=True
    )


def get_config(use_cache=True):
    """Get config from SSM with optional caching."""
    global _config_cache
    now = time.time()
    if use_cache and _config_cache[0] is not None and (now - _config_cache[1]) < CONFIG_CACHE_TTL:
        return _config_cache[0]

    param_name = os.environ.get('CONFIG_PARAMETER_NAME', 'CloudWatchAlarmWidgetConfigCDK')
    config = json.loads(get_parameter_from_store(param_name))

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


def validate_region(region):
    """Validate an AWS region string."""
    if re.match(r'^[a-z]{2}-[a-z]+-\d+$', str(region)):
        return region
    return "none"


def validate_account_id(account_id):
    """Validate an AWS account ID."""
    if re.match(r'^\d{12}$', str(account_id)):
        return account_id
    return "none"


def validate_state(state):
    """Validate an alarm state value."""
    if state in ('OK', 'ALARM', 'INSUFFICIENT_DATA', 'none'):
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
    """Apply filter parameters from event to config. Returns (config, changed)."""
    changed = False

    if 'region' in event:
        new_val = validate_region(event['region']) if event['region'] != 'none' else 'none'
        if config.get('region_filter') != new_val:
            config['region_filter'] = new_val
            changed = True

    if 'account' in event:
        new_val = validate_account_id(event['account']) if event['account'] != 'none' else 'none'
        if config.get('account_filter') != new_val:
            config['account_filter'] = new_val
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


def get_filter_icon(color_code):
    """Return filter icon SVG with the specified color."""
    return FILTER_ICON_SVG.replace('{color}', color_code)


def get_suppress_icon():
    """Return suppress (X) icon SVG."""
    return SUPPRESS_ICON_SVG
