import boto3
import json
from botocore.exceptions import ClientError

ec2 = boto3.client('ec2')
events = boto3.client('events')
cw = boto3.client('cloudwatch')
acct = boto3.client('account')


def is_expression_alarm(alarm):
    for metric in alarm["detail"]["configuration"]["metrics"]:
        if 'expression' in metric:
            return True

    return False


def get_alarm_type(alarm):
    if "metrics" not in alarm["detail"]["configuration"]:
        return "composite"
    elif is_expression_alarm(alarm):
        return "expression"
    else:
        return "standard"


def get_ec2_instance_info(instance_id):
    # TODO: Implement Pagination
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        return response['Reservations'][0]['Instances'][0]
    except:
        return []


def forward_event(event):
    events.put_events(Entries=[{
        'Source': 'aws-ec2-instance-info',
        'DetailType': 'Instance Info',
        'Detail': event,
        'EventBusName': 'arn:aws:events:eu-west-1:804485321675:event-bus/CWAlarmEventBus'
        }]
    )


def get_alarm_tags(alarm_arn):
    response = cw.list_tags_for_resource(
        ResourceARN=alarm_arn
    )
    print(json.dumps(response))
    return response


def lambda_handler(event, context):
    print(json.dumps(event))
    payload = {}
    event_sent = False
    payload['AlarmName'] = event["detail"]["alarmName"]
    payload['Account'] = event["account"]
    alarm_tags = get_alarm_tags(event["resources"][0])['Tags']
    print(json.dumps(alarm_tags))
    payload['AlarmTags'] = alarm_tags
    if len(alarm_tags) == 0:
        payload['Priority'] = 2
    else:
        for tag in alarm_tags:
            if tag['Key'].lower() == 'priority':
                match tag['Value'].lower():
                    case 'high':
                        payload['Priority'] = 1
                    case "critical":
                        payload['Priority'] = 1
                    case "urgent":
                        payload['Priority'] = 1
                    case "medium":
                        payload['Priority'] = 2
                    case "standard":
                        payload['Priority'] = 2
                    case "normal":
                        payload['Priority'] = 2
                    case "low":
                        payload['Priority'] = 3
                    case _:
                        payload['Priority'] = 2
                break
    try:
        result = acct.get_alternate_contact(
            AlternateContactType='OPERATIONS'
        )
        payload['AlternateContact'] = result['AlternateContact']
        print(f'Contact: {result["AlternateContact"]}')
    except:
        print('Account has no OPERATIONS contact or request failed')

    if get_alarm_type(event) == "standard":
        for metric in event["detail"]["configuration"]["metrics"]:
            if "metricStat" in metric and not event_sent:
                for dimension in list(metric["metricStat"]["metric"]["dimensions"].keys()):
                    try:
                        if dimension == "InstanceId":
                            instance_id = metric["metricStat"]["metric"]["dimensions"][dimension]
                            instance_info = get_ec2_instance_info(instance_id)
                            print(instance_info)
                            if len(instance_info) == 0:
                                payload['InstanceInfo'] = {'Error': 'Instance not found'}
                            else:
                                payload['InstanceInfo'] = instance_info
                            print('PAYLOAD')
                            print(payload)
                            forward_event(json.dumps(payload, indent=4, sort_keys=True, default=str))
                            event_sent = True
                            break
                    except ClientError as error:
                        print('Error happened: {}'.format(error))
                        continue
            else:
                print("Ignoring metric")
    else:
        print(json.dumps(payload, indent=4, sort_keys=True, default=str))
        forward_event(json.dumps(payload, indent=4, sort_keys=True, default=str))