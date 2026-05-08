"""Unit tests for shared utility functions."""

import pytest
from shared.utils import (
    safe_html,
    sanitize_filter_value,
    validate_region,
    validate_account_id,
    validate_state,
    validate_priority,
    apply_filters_from_event,
    get_alarm_type,
    is_expression_alarm,
    get_filter_icon,
    get_suppress_icon,
    get_unsuppress_icon,
)


class TestSafeHtml:
    """Tests for XSS prevention via HTML escaping."""

    def test_escapes_script_tags(self):
        assert '&lt;script&gt;' in safe_html('<script>alert(1)</script>')

    def test_escapes_angle_brackets(self):
        result = safe_html('<img src=x onerror=alert(1)>')
        assert '<img' not in result
        assert '&lt;' in result

    def test_escapes_quotes(self):
        result = safe_html('" onmouseover="alert(1)"')
        assert '&quot;' in result

    def test_handles_none(self):
        assert safe_html(None) == ''

    def test_handles_normal_text(self):
        assert safe_html('Normal alarm name') == 'Normal alarm name'

    def test_handles_ampersand(self):
        assert safe_html('A & B') == 'A &amp; B'


class TestValidateRegion:
    """Tests for AWS region validation."""

    def test_valid_region(self):
        assert validate_region('us-east-1') == 'us-east-1'
        assert validate_region('eu-west-1') == 'eu-west-1'
        assert validate_region('ap-southeast-2') == 'ap-southeast-2'

    def test_invalid_region(self):
        assert validate_region('invalid') == 'none'
        assert validate_region('') == 'none'
        assert validate_region('<script>') == 'none'
        assert validate_region('us-east-1; DROP TABLE') == 'none'


class TestValidateAccountId:
    """Tests for AWS account ID validation."""

    def test_valid_account_id(self):
        assert validate_account_id('123456789012') == '123456789012'

    def test_invalid_account_id(self):
        assert validate_account_id('12345') == 'none'
        assert validate_account_id('abcdefghijkl') == 'none'
        assert validate_account_id('') == 'none'
        assert validate_account_id('1234567890123') == 'none'


class TestValidateState:
    """Tests for alarm state validation."""

    def test_valid_states(self):
        assert validate_state('OK') == 'OK'
        assert validate_state('ALARM') == 'ALARM'
        assert validate_state('INSUFFICIENT_DATA') == 'INSUFFICIENT_DATA'
        assert validate_state('none') == 'none'

    def test_invalid_states(self):
        assert validate_state('invalid') == 'none'
        assert validate_state('') == 'none'
        assert validate_state('<script>') == 'none'


class TestValidatePriority:
    """Tests for priority validation."""

    def test_valid_priority(self):
        assert validate_priority(1) == 1
        assert validate_priority(2) == 2
        assert validate_priority(3) == 3
        assert validate_priority('1') == 1

    def test_invalid_priority(self):
        assert validate_priority(0) == 'none'
        assert validate_priority(4) == 'none'
        assert validate_priority('invalid') == 'none'
        assert validate_priority(None) == 'none'


class TestSanitizeFilterValue:
    """Tests for general filter value sanitization."""

    def test_normal_values(self):
        assert sanitize_filter_value('us-east-1') == 'us-east-1'
        assert sanitize_filter_value('123456789012') == '123456789012'

    def test_rejects_long_values(self):
        assert sanitize_filter_value('a' * 257) == 'none'

    def test_handles_none(self):
        assert sanitize_filter_value(None) == 'none'

    def test_strips_whitespace(self):
        assert sanitize_filter_value('  us-east-1  ') == 'us-east-1'


class TestApplyFiltersFromEvent:
    """Tests for filter application logic."""

    def test_applies_region_filter(self):
        config = {}
        event = {'region': 'us-east-1'}
        result, changed = apply_filters_from_event(event, config)
        assert result['region_filter'] == 'us-east-1'
        assert changed is True

    def test_applies_account_filter(self):
        config = {}
        event = {'account': '123456789012'}
        result, changed = apply_filters_from_event(event, config)
        assert result['account_filter'] == '123456789012'
        assert changed is True

    def test_clears_filter_with_none(self):
        config = {'region_filter': 'us-east-1'}
        event = {'region': 'none'}
        result, changed = apply_filters_from_event(event, config)
        assert result['region_filter'] == 'none'
        assert changed is True

    def test_no_change_returns_false(self):
        config = {'region_filter': 'us-east-1'}
        event = {}
        result, changed = apply_filters_from_event(event, config)
        assert changed is False

    def test_rejects_invalid_region(self):
        config = {}
        event = {'region': '<script>alert(1)</script>'}
        result, changed = apply_filters_from_event(event, config)
        assert result['region_filter'] == 'none'

    def test_applies_page_number(self):
        config = {}
        event = {'currentAlarmViewPage': '5'}
        result, changed = apply_filters_from_event(event, config)
        assert result['currentAlarmViewPage'] == 5
        assert changed is True


class TestGetAlarmType:
    """Tests for alarm type detection."""

    def test_standard_alarm(self, sample_alarm_event):
        assert get_alarm_type(sample_alarm_event) == 'standard'

    def test_composite_alarm(self, sample_composite_alarm_event):
        assert get_alarm_type(sample_composite_alarm_event) == 'composite'

    def test_expression_alarm(self, sample_expression_alarm_event):
        assert get_alarm_type(sample_expression_alarm_event) == 'expression'


class TestIsExpressionAlarm:
    """Tests for expression alarm detection."""

    def test_expression_alarm(self, sample_expression_alarm_event):
        assert is_expression_alarm(sample_expression_alarm_event) is True

    def test_standard_alarm(self, sample_alarm_event):
        assert is_expression_alarm(sample_alarm_event) is False

    def test_composite_alarm(self, sample_composite_alarm_event):
        # Composite alarms have no metrics key
        assert is_expression_alarm(sample_composite_alarm_event) is False


class TestIcons:
    """Tests for icon generation functions."""

    def test_filter_icon_contains_svg(self):
        result = get_filter_icon('ff0000')
        assert '<svg' in result
        assert 'ff0000' in result

    def test_filter_icon_color_change(self):
        black = get_filter_icon('000000')
        red = get_filter_icon('ff0000')
        assert '000000' in black
        assert 'ff0000' in red

    def test_suppress_icon_returns_svg(self):
        assert '<svg' in get_suppress_icon()

    def test_unsuppress_icon_returns_svg(self):
        assert '<svg' in get_unsuppress_icon()
        assert '#4CAF50' in get_unsuppress_icon()
