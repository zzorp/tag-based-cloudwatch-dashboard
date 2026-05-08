"""Unit tests for alarm_list Lambda function helpers."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'functions'))

from alarm_list.app import (
    paginate_items,
    get_account_list,
    get_region_list,
    build_pagination_html,
    build_filter_popup,
    build_clear_filter_action,
)


class TestPaginateItems:
    """Tests for pagination logic."""

    def test_first_page(self):
        items = list(range(25))
        result = paginate_items(items, 1, 10)
        assert result == list(range(10))

    def test_second_page(self):
        items = list(range(25))
        result = paginate_items(items, 2, 10)
        assert result == list(range(10, 20))

    def test_last_page_partial(self):
        items = list(range(25))
        result = paginate_items(items, 3, 10)
        assert result == list(range(20, 25))

    def test_page_beyond_max_returns_last(self):
        items = list(range(25))
        result = paginate_items(items, 99, 10)
        assert result == list(range(20, 25))

    def test_page_zero_returns_first(self):
        items = list(range(25))
        result = paginate_items(items, 0, 10)
        assert result == list(range(10))

    def test_empty_items(self):
        result = paginate_items([], 1, 10)
        assert result == []

    def test_single_page(self):
        items = list(range(5))
        result = paginate_items(items, 1, 10)
        assert result == list(range(5))


class TestGetAccountList:
    """Tests for account list extraction."""

    def test_extracts_unique_accounts(self):
        alarms = [
            {'alarmKey': '111111111111#Alarm1#us-east-1'},
            {'alarmKey': '222222222222#Alarm2#eu-west-1'},
            {'alarmKey': '111111111111#Alarm3#us-east-1'},
        ]
        result = get_account_list(alarms)
        assert result == ['111111111111', '222222222222']

    def test_empty_alarms(self):
        assert get_account_list([]) == []


class TestGetRegionList:
    """Tests for region list extraction."""

    def test_extracts_unique_regions(self):
        alarms = [
            {'alarmKey': '111111111111#Alarm1#us-east-1'},
            {'alarmKey': '222222222222#Alarm2#eu-west-1'},
            {'alarmKey': '111111111111#Alarm3#us-east-1'},
        ]
        result = get_region_list(alarms)
        assert sorted(result) == ['eu-west-1', 'us-east-1']

    def test_handles_missing_region(self):
        alarms = [
            {'alarmKey': '111111111111#Alarm1'},
        ]
        result = get_region_list(alarms)
        assert result == []


class TestBuildPaginationHtml:
    """Tests for pagination HTML generation."""

    def test_single_page_returns_empty(self):
        result = build_pagination_html(1, 1, 'arn:test')
        assert result == ''

    def test_includes_prev_button_on_page_2(self):
        result = build_pagination_html(2, 5, 'arn:test')
        assert 'Prev' in result

    def test_no_prev_on_first_page(self):
        result = build_pagination_html(1, 5, 'arn:test')
        assert 'Prev' not in result

    def test_includes_next_button(self):
        result = build_pagination_html(1, 5, 'arn:test')
        assert 'Next' in result

    def test_no_next_on_last_page(self):
        result = build_pagination_html(5, 5, 'arn:test')
        assert 'Next' not in result

    def test_marks_current_page(self):
        result = build_pagination_html(3, 10, 'arn:test')
        assert 'current-page' in result


class TestBuildFilterPopup:
    """Tests for filter popup HTML generation."""

    def test_includes_all_options(self):
        options = [
            {'label': 'OK', 'value': 'OK'},
            {'label': 'ALARM', 'value': 'ALARM'},
        ]
        result = build_filter_popup('arn:test', 'state', options)
        assert 'OK' in result
        assert 'ALARM' in result

    def test_uses_correct_filter_type(self):
        options = [{'label': 'us-east-1', 'value': 'us-east-1'}]
        result = build_filter_popup('arn:test', 'region', options)
        assert '"region"' in result


class TestBuildClearFilterAction:
    """Tests for clear filter action HTML."""

    def test_clears_with_none(self):
        result = build_clear_filter_action('arn:test', 'state')
        assert '"state": "none"' in result
        assert 'Remove this filter' in result
