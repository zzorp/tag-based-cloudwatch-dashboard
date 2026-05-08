"""Shared pytest fixtures for alarm dashboard Lambda tests."""

import sys
import os
import pytest

# Add functions directory to path so shared module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'functions'))


@pytest.fixture
def sample_alarm_event():
    """A standard CloudWatch Alarm state change event."""
    return {
        "version": "0",
        "id": "test-event-id",
        "detail-type": "CloudWatch Alarm State Change",
        "source": "aws.cloudwatch",
        "account": "123456789012",
        "time": "2024-01-15T10:30:00Z",
        "region": "us-east-1",
        "resources": ["arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm"],
        "detail": {
            "alarmName": "TestAlarm",
            "state": {
                "value": "ALARM",
                "reason": "Threshold crossed",
                "timestamp": "2024-01-15T10:30:00.000+0000"
            },
            "previousState": {
                "value": "OK",
                "reason": "Threshold ok",
                "timestamp": "2024-01-15T09:00:00.000+0000"
            },
            "configuration": {
                "metrics": [
                    {
                        "metricStat": {
                            "metric": {
                                "namespace": "AWS/EC2",
                                "name": "CPUUtilization",
                                "dimensions": {
                                    "InstanceId": "i-1234567890abcdef0"
                                }
                            },
                            "stat": "Average",
                            "period": 300
                        }
                    }
                ]
            }
        }
    }


@pytest.fixture
def sample_composite_alarm_event():
    """A composite CloudWatch Alarm state change event."""
    return {
        "version": "0",
        "id": "test-composite-event",
        "detail-type": "CloudWatch Alarm State Change",
        "source": "aws.cloudwatch",
        "account": "123456789012",
        "time": "2024-01-15T10:30:00Z",
        "region": "eu-west-1",
        "resources": ["arn:aws:cloudwatch:eu-west-1:123456789012:alarm:CompositeTestAlarm"],
        "detail": {
            "alarmName": "CompositeTestAlarm",
            "state": {
                "value": "ALARM",
                "reason": "Composite alarm rule triggered",
                "timestamp": "2024-01-15T10:30:00.000+0000"
            },
            "configuration": {
                "alarmRule": "ALARM(ChildAlarm1) OR ALARM(ChildAlarm2)"
            }
        }
    }


@pytest.fixture
def sample_expression_alarm_event():
    """A metric math expression CloudWatch Alarm state change event."""
    return {
        "version": "0",
        "id": "test-expression-event",
        "detail-type": "CloudWatch Alarm State Change",
        "source": "aws.cloudwatch",
        "account": "987654321098",
        "time": "2024-01-15T10:30:00Z",
        "region": "ap-southeast-1",
        "resources": ["arn:aws:cloudwatch:ap-southeast-1:987654321098:alarm:ExpressionAlarm"],
        "detail": {
            "alarmName": "ExpressionAlarm",
            "state": {
                "value": "OK",
                "reason": "Threshold ok",
                "timestamp": "2024-01-15T10:30:00.000+0000"
            },
            "configuration": {
                "metrics": [
                    {
                        "expression": "m1/m2*100",
                        "label": "Error Rate",
                        "id": "e1"
                    },
                    {
                        "metricStat": {
                            "metric": {
                                "namespace": "AWS/ApiGateway",
                                "name": "5XXError",
                                "dimensions": {
                                    "ApiName": "MyAPI"
                                }
                            },
                            "stat": "Sum",
                            "period": 300
                        },
                        "id": "m1"
                    }
                ]
            }
        }
    }


@pytest.fixture
def sample_dynamo_alarm_item():
    """A DynamoDB alarm item as stored in the table."""
    return {
        "alarmKey": "123456789012#TestAlarm#us-east-1",
        "stateValue": "ALARM",
        "suppressed": 0,
        "priority": 1,
        "detail": {
            "alarmName": "TestAlarm",
            "state": {
                "value": "ALARM",
                "reason": "Threshold crossed",
                "timestamp": "2024-01-15T10:30:00.000+0000"
            },
            "configuration": {
                "metrics": [
                    {
                        "metricStat": {
                            "metric": {
                                "namespace": "AWS/EC2",
                                "name": "CPUUtilization",
                                "dimensions": {
                                    "InstanceId": "i-1234567890abcdef0"
                                }
                            }
                        }
                    }
                ]
            }
        },
        "auxiliaryInfo": {
            "AlternateContact": {
                "Name": "John Doe",
                "EmailAddress": "john@example.com",
                "PhoneNumber": "+1234567890"
            },
            "Account": {
                "Id": "123456789012",
                "Status": "ACTIVE",
                "Email": "account@example.com"
            }
        },
        "alarmTags": [
            {"Key": "priority", "Value": "critical"},
            {"Key": "team", "Value": "platform"}
        ]
    }
