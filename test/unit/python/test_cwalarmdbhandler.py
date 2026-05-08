"""Unit tests for cwalarmdbhandler Lambda function."""

import pytest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add functions to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'functions'))


class TestGetPriority:
    """Tests for priority extraction from alarm tags."""

    def setup_method(self):
        # Mock boto3 before importing
        with patch.dict(os.environ, {
            'DYNAMO_TABLE_NAME': 'TestTable',
            'CONFIG_PARAMETER_NAME': 'TestParam'
        }):
            with patch('boto3.resource'), patch('boto3.client'):
                from cwalarmdbhandler.app import get_priority
                self.get_priority = get_priority

    def test_critical_priority(self):
        tags = [{'Key': 'priority', 'Value': 'critical'}]
        assert self.get_priority(tags) == 1

    def test_high_priority(self):
        tags = [{'Key': 'priority', 'Value': 'high'}]
        assert self.get_priority(tags) == 1

    def test_urgent_priority(self):
        tags = [{'Key': 'priority', 'Value': 'urgent'}]
        assert self.get_priority(tags) == 1

    def test_medium_priority(self):
        tags = [{'Key': 'priority', 'Value': 'medium'}]
        assert self.get_priority(tags) == 2

    def test_standard_priority(self):
        tags = [{'Key': 'priority', 'Value': 'standard'}]
        assert self.get_priority(tags) == 2

    def test_low_priority(self):
        tags = [{'Key': 'priority', 'Value': 'low'}]
        assert self.get_priority(tags) == 3

    def test_default_priority_no_tag(self):
        tags = [{'Key': 'other', 'Value': 'something'}]
        assert self.get_priority(tags) == 2

    def test_empty_tags(self):
        assert self.get_priority([]) == 2

    def test_case_insensitive(self):
        tags = [{'Key': 'Priority', 'Value': 'CRITICAL'}]
        assert self.get_priority(tags) == 1

    def test_unknown_value_defaults_medium(self):
        tags = [{'Key': 'priority', 'Value': 'unknown'}]
        assert self.get_priority(tags) == 2


class TestGetResourceType:
    """Tests for resource type detection from metrics."""

    def setup_method(self):
        with patch.dict(os.environ, {
            'DYNAMO_TABLE_NAME': 'TestTable',
            'CONFIG_PARAMETER_NAME': 'TestParam'
        }):
            with patch('boto3.resource'), patch('boto3.client'):
                from cwalarmdbhandler.app import get_resource_type
                self.get_resource_type = get_resource_type

    def test_ec2_instance(self):
        metrics = [{"metricStat": {"metric": {"dimensions": {"InstanceId": "i-123"}}}}]
        assert self.get_resource_type(metrics) == "ec2_instance"

    def test_ddb_table(self):
        metrics = [{"metricStat": {"metric": {"dimensions": {"TableName": "MyTable"}}}}]
        assert self.get_resource_type(metrics) == "ddb_table"

    def test_unknown_resource(self):
        metrics = [{"metricStat": {"metric": {"dimensions": {"QueueName": "MyQueue"}}}}]
        assert self.get_resource_type(metrics) == "Unknown"

    def test_expression_metric_skipped(self):
        metrics = [{"expression": "m1/m2", "id": "e1"}]
        assert self.get_resource_type(metrics) == "Unknown"


class TestGetAlarmType:
    """Tests for alarm type classification."""

    def setup_method(self):
        with patch.dict(os.environ, {
            'DYNAMO_TABLE_NAME': 'TestTable',
            'CONFIG_PARAMETER_NAME': 'TestParam'
        }):
            with patch('boto3.resource'), patch('boto3.client'):
                from cwalarmdbhandler.app import get_alarm_type
                self.get_alarm_type = get_alarm_type

    def test_standard_alarm(self, sample_alarm_event):
        assert self.get_alarm_type(sample_alarm_event) == "standard"

    def test_composite_alarm(self, sample_composite_alarm_event):
        assert self.get_alarm_type(sample_composite_alarm_event) == "composite"

    def test_expression_alarm(self, sample_expression_alarm_event):
        assert self.get_alarm_type(sample_expression_alarm_event) == "expression"


class TestAugmentEvent:
    """Tests for event augmentation with error resilience."""

    def setup_method(self):
        self.env_patch = patch.dict(os.environ, {
            'DYNAMO_TABLE_NAME': 'TestTable',
            'CONFIG_PARAMETER_NAME': 'TestParam'
        })
        self.env_patch.start()

    def teardown_method(self):
        self.env_patch.stop()

    @patch('boto3.resource')
    @patch('boto3.client')
    def test_augmentation_failure_preserves_event(self, mock_client, mock_resource, sample_alarm_event):
        """If augmentation fails, the event should still have default values."""
        # Make all augmentation calls fail
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {'Account': '999999999999'}
        mock_sts.assume_role.side_effect = Exception("Access denied")
        mock_client.return_value = mock_sts

        from cwalarmdbhandler.app import augment_event
        result = augment_event(sample_alarm_event)

        # Event should still have basic structure
        assert 'AuxiliaryInfo' in result
        assert 'Account' in result['AuxiliaryInfo']
        assert result['AuxiliaryInfo']['Account']['Id'] == '123456789012'
        # Priority should default
        assert result['Priority'] == 2
        assert result['AlarmTags'] == []
