from time import sleep
import time
import os
import boto3
import pandas as pd
import numpy as np
import datetime
import urllib.request, json 
import requests
import adal
import math
from http.server import BaseHTTPRequestHandler, HTTPServer
from functools import partial 
from typing import List, Dict
import threading
import sys
from collections import defaultdict 

import rejuvenation

US_REGIONS = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']
clients = {}
region = US_REGIONS[0]
current_type = 't2.micro'
capacity = 2
INSTANCE_MANAGER_INSTANCE_ID = "i-035f88ca820e399e7"
CLIENT_INSTANCE_ID = "i-0c7adc535b262d69e"
SERVICE_INSTANCE_ID = "i-0dd2ca9d91838f3c8"

def pretty_json(obj):
    return json.dumps(obj, sort_keys=True, indent=4, default=str)

def parse_input_args(filename):
    with open(filename, 'r') as j:
        input_args = json.loads(j.read())
        # Convert to list of keys only:
        # excluded_instances = list(cred_json.values())
        # print(excluded_instances)
    return input_args

def choose_session(region):
    ec2 = boto3.client('ec2', region)
    ce = boto3.client('ce')
    return ec2, ce

def chunks(lst, n):
    """
        Breaks a list into equally sized chunks of size n.
        Parameters:
            lst: list
            n: int

        https://stackoverflow.com/a/312464/13336187

        Usage example: list(chunks(range(10, 75), 10)
    """
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def get_instance_type(ec2, types):
    response = ec2.describe_instance_types(
        InstanceTypes=types
    )
    return response

def get_max_nics(ec2, instance_type):
    response = ec2.describe_instance_types(
        InstanceTypes=[
            instance_type,
        ],
        # Filters=[
        #     {
        #         'Name': 'network-info.maximum-network-interfaces',
        #         'Values': [
        #             'string',
        #         ]
        #     },
        # ],
    )

    # print(pretty_json(response))

    return int(response['InstanceTypes'][0]['NetworkInfo']['MaximumNetworkInterfaces'])

def update_spot_prices(ec2):
    responses = ec2.describe_spot_price_history(
        ProductDescriptions=['Linux/UNIX'],
        StartTime=datetime.datetime.utcnow(),
    )
    spot_prices: List[Dict[str, str]] = []
    #get instance types in a batch of 50
    item_count = len(responses['SpotPriceHistory'])
    batch_size = 100
    type_to_NIC = {}
    for i in range(0, item_count, batch_size):
        batch = responses['SpotPriceHistory'][i:i+batch_size]
        instance_types = []
        for response in batch:
            instance_types.append(response['InstanceType'])
        #get instance types
        instance_types_response = ec2.describe_instance_types(
            InstanceTypes=instance_types
        )
        #add instance types to spot price history
        for response in instance_types_response['InstanceTypes']:
            type_to_NIC[response['InstanceType']] = response['NetworkInfo']['MaximumNetworkInterfaces']
    #add price per interface to spot price history
    for response in responses['SpotPriceHistory']:
        spot_prices.append({
            'AvailabilityZone': response['AvailabilityZone'],
            'InstanceType': response['InstanceType'],
            'MaximumNetworkInterfaces': type_to_NIC[response['InstanceType']],
            'SpotPrice': float(response['SpotPrice']),
            'PricePerInterface': (float(response['SpotPrice']) + 0.005 * (type_to_NIC[response['InstanceType']] - 1)) / type_to_NIC[response['InstanceType']],
            'Timestamp': response['Timestamp']  
        })
    df = pd.DataFrame(spot_prices)
    #write to csv
    df.to_csv('misc/logs/spot_prices.csv')
    return df

def update_azure_vm_sizes():
    token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IjVCM25SeHRRN2ppOGVORGMzRnkwNUtmOTdaRSIsImtpZCI6IjVCM25SeHRRN2ppOGVORGMzRnkwNUtmOTdaRSJ9.eyJhdWQiOiJodHRwczovL21hbmFnZW1lbnQuY29yZS53aW5kb3dzLm5ldCIsImlzcyI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0L2JhZjBkNjVjLWM3NzQtNDA0MC1hMWE2LTBmZjAzZmQ2MWRkNi8iLCJpYXQiOjE3MDUwMDUwMDEsIm5iZiI6MTcwNTAwNTAwMSwiZXhwIjoxNzA1MDA5MjM4LCJhY3IiOiIxIiwiYWlvIjoiQVdRQW0vOFZBQUFBQyt5bVpJdTNxdU01TUk5V3c4ZnlrODcrQ3JaY2duTG1FV0JZUUVRRkczR3NCWUROSEZ0S3BuSDhJcWlEbWVYUC9WRGF4VnVWdkIwOTV0VVpBdDVzYmE1NzJYSkE0UFJ3bElXeFByTHZUVjRPQk9aMWZFMHZSWlVxdk84dnZ6NDkiLCJhbXIiOlsicHdkIl0sImFwcGlkIjoiMThmYmNhMTYtMjIyNC00NWY2LTg1YjAtZjdiZjJiMzliM2YzIiwiYXBwaWRhY3IiOiIwIiwiZmFtaWx5X25hbWUiOiJQZWkiLCJnaXZlbl9uYW1lIjoiSmlueXUiLCJncm91cHMiOlsiYmVjZWJlNTUtOTBhZi00ZjAzLWFiNjUtYjE3ZGYyMDVjOGRjIiwiMGY5OTJkN2UtMDMxYS00M2Y0LWJjZmQtMmU0YzMwMzY5YWMwIiwiMmU3ZGZjZjQtNzBlOC00MGQxLWJkNjktNDMyMjJlYjgwOGEyIl0sImlkdHlwIjoidXNlciIsImlwYWRkciI6IjE2OC41LjE4NS4yNiIsIm5hbWUiOiJKaW55dSBQZWkiLCJvaWQiOiJhZmQ2YjA1Zi1jYzA2LTQzZmUtOGVjMy1hZTkwMWUwNGFjMDciLCJvbnByZW1fc2lkIjoiUy0xLTUtMjEtMzk4MTcxODI5Mi0zMTQ3MDE3NDM3LTI0NTU3MjQyOTctMjU2OTMxIiwicHVpZCI6IjEwMDMyMDAwRDY4QjkzREEiLCJyaCI6IjAuQVZrQVhOYnd1blRIUUVDaHBnX3dQOVlkMWtaSWYza0F1dGRQdWtQYXdmajJNQk5aQVBFLiIsInNjcCI6InVzZXJfaW1wZXJzb25hdGlvbiIsInN1YiI6ImZwSU1zUGo2TGpxMHhOQ1FVTEM3NzlnVy1GQ3poWDV0Rk9hTTZzOVA2WTgiLCJ0aWQiOiJiYWYwZDY1Yy1jNzc0LTQwNDAtYTFhNi0wZmYwM2ZkNjFkZDYiLCJ1bmlxdWVfbmFtZSI6ImpwOTVAcmljZS5lZHUiLCJ1cG4iOiJqcDk1QHJpY2UuZWR1IiwidXRpIjoiUnVyNllqQ3lyVTJFV1Q0RmFMby1BQSIsInZlciI6IjEuMCIsIndpZHMiOlsiYjc5ZmJmNGQtM2VmOS00Njg5LTgxNDMtNzZiMTk0ZTg1NTA5Il0sInhtc19jYWUiOiIxIiwieG1zX3RjZHQiOjE1OTQ5MTg2MzF9.0-p5FaqFZQJ3UmB6Hg6UwQEGFm6-3p_bFRTt5OaBtJTqZjYefUjOpUyPAIXMVaPm-f8euCgx1JMv4zgwp63spcgFG370nUYmzfBWX_dCSaoWI2fCdRbxW3Z9qEEEo1sJIQ08HR7WORdWQcreWuOdZmGoRhwU_P78SdTW90-hnqIRQvggGN7_WGcN1_HxIcyrsa09v5pIXrad_noJsmCiwUvRmXBq2PFi5IbHs2vn5qbOEE_9d2xpK_cO48YtuctTmYPe5D1ATEzIR3ENNaNpH5EimvhOsCWHdmGsZ4DBZHoGBStQZBiAl_YmJ5vD9F-e_gcIGnw083Qy5xkdAfC3vw"
    url = "https://management.azure.com/subscriptions/0e51cc83-16a9-4ea1-b6f9-ba23ddfcc8bf/providers/Microsoft.Compute/skus?api-version=2021-07-01&$filter=location eq 'eastus'"
    headers = {
        "Authorization": "Bearer " + token
    }
    max_nic = {}
    next_page_link = url
    while next_page_link != None:
        response = requests.get(next_page_link, headers=headers)
        data = response.json()
        for item in data['value']:
            if "capabilities" in item.keys():
                capabilities = item['capabilities']
                for c_item in capabilities:
                    if c_item['name'] == 'MaxNetworkInterfaces':
                        max_nic[item['name']] = c_item['value']
        next_page_link = None
    #write to csv
    df = pd.DataFrame(max_nic.items(), columns=['InstanceType', 'MaximumNetworkInterfaces'])
    df.to_csv('azure_vm_sizes.csv')


def update_azure_prices(update_nic=False):
    if update_nic:
        update_azure_vm_sizes()
    nic_info = pd.read_csv('azure_vm_sizes.csv')
    next_page_link = "https://prices.azure.com/api/retail/prices?$skip=0&$filter=serviceName%20eq%20%27Virtual%20Machines%27%20and%20priceType%20eq%20%27Consumption%27%20and%20armRegionName%20eq%20%27eastus%27"
    spot_prices: List[Dict[str, str]] = []
    while next_page_link != None:
        with urllib.request.urlopen(next_page_link) as url:
            data = json.loads(url.read().decode())
            for item in data['Items']:
                if 'Spot' in item['skuName']:
                    instance_type_name = item['skuName'].split('Spot')[0].strip()
                    if instance_type_name in nic_info['InstanceType'].values:
                        nic = nic_info.loc[nic_info['InstanceType'] == instance_type_name]['MaximumNetworkInterfaces'].values[0]
                        spot_prices.append({
                            'AvailabilityZone': item['location'],
                            'InstanceType': item['skuName'],
                            'MaximumNetworkInterfaces': nic,
                            'SpotPrice': item['retailPrice'],
                            'PricePerInterface': item['retailPrice'] / nic + nic * 0.005,
                            'Timestamp': item['effectiveStartDate']  
                        })
                    else:
                        spot_prices.append({
                            'AvailabilityZone': item['location'],
                            'InstanceType': item['skuName'],
                            'MaximumNetworkInterfaces': 1,
                            'SpotPrice': item['retailPrice'],
                            'PricePerInterface': item['retailPrice'],
                            'Timestamp': item['effectiveStartDate']  
                        })
            next_page_link = data['NextPageLink']
    df = pd.DataFrame(spot_prices)
    #write to csv
    df.to_csv('misc/logs/azure_spot_prices.csv')
    return df

def merge_spot_prices():
    aws_spot_prices = pd.read_csv('misc/logs/spot_prices.csv')
    azure_spot_prices = pd.read_csv('misc/logs/azure_spot_prices.csv')
    aws_spot_prices['Provider'] = 'AWS'
    azure_spot_prices['Provider'] = 'Azure'
    spot_prices = pd.concat([aws_spot_prices, azure_spot_prices])
    spot_prices['Timestamp'] = pd.to_datetime(spot_prices['Timestamp'])
    spot_prices = spot_prices.sort_values(by=['Timestamp'])
    spot_prices.to_csv('misc/logs/total_spot_prices.csv')
    return spot_prices

def get_spot_prices():
    df = pd.read_csv('misc/logs/spot_prices.csv')
    return df

def get_all_instances(ec2):
    response = ec2.describe_instances()
    # response['Reservations'][0]['Instances'][0]['InstanceId']
    # print(pretty_json(response))
    instance_ids = [instance['InstanceId'] for instance in extract_instance_details_from_describe_instances_response(response)]
    return instance_ids

def get_all_running_instances(ec2):
    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'instance-state-name',
                'Values': [
                    'running',
                ]
            }
    ])
    # response['Reservations'][0]['Instances'][0]['InstanceId']
    # print(pretty_json(response))
    instance_ids = [instance['InstanceId'] for instance in extract_instance_details_from_describe_instances_response(response)]
    return instance_ids

def extract_instance_details_from_describe_instances_response(response):
    """
        Purpose: each element of the response['Reservations'] list only holds 25 instances. 
    """
    instance_list = []
    for i in response['Reservations']:
        instance_list.extend(i['Instances'])
    return instance_list

def get_excluded_terminate_instances():
    # Get excluded from termination instance list:
    excluded_instances = []
    with open("misc/exclude-from-termination-list.json", 'r') as j:
        cred_json = json.loads(j.read())
        # Convert to list of keys only:
        excluded_instances = list(cred_json.values())
        # print(excluded_instances)
    return excluded_instances

def get_all_instances_init_details(ec2):
    """
        Used only for wireguard integration only for now: GET endpoint
    """
    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'instance-state-name',
                'Values': [
                    'running',
                ]
            }
        ]
    )
    # Get excluded from termination instance list:
    excluded_instances = get_excluded_terminate_instances()
    # response['Reservations'][0]['Instances'][0]['InstanceId']
    return extract_init_details_from_describe_instances_response(response, excluded_instances)

def extract_init_details_from_describe_instances_response(response, excluded_instances):
    instances_details = defaultdict(dict)
    for instance in extract_instance_details_from_describe_instances_response(response):
        # print(instance['InstanceId'])
        if instance['InstanceId'] not in excluded_instances: # no need to include instance manager since we will not assign clients to it anyway..
            instances_details[instance['InstanceId']] = {"PublicIpAddress": instance['PublicIpAddress']}
    # instance_ids = [instance['InstanceId'] for instance in response['Reservations'][0]['Instances']]
    return instances_details

def get_specific_instances_attached_ebs(ec2, instance_id):
    """
        Get an instance's attached NIC EBS volume details. 
    """
    
    volumes = ec2.describe_instance_attribute(InstanceId=instance_id,
        Attribute='blockDeviceMapping')
    # Get ec2 instance attached NIC IDs:
    # nics = ec2.describe_instance_attribute(InstanceId=instance_id,
    #     Attribute='networkInterfaceSet')
    return volumes 

def get_specific_instances(ec2, instance_ids):
    response = ec2.describe_instances(
        InstanceIds=instance_ids
    )
    return response

def get_specific_instances_with_fleet_id_tag(ec2, fleet_id, return_type="init-details"):
    """
        tag:<key> - The key/value combination of a tag assigned to the resource. Use the tag key in the filter name and the tag value as the filter value. For example, to find all resources that have a tag with the key Owner and the value TeamA, specify tag:Owner for the filter name and TeamA for the filter value.

        Parameters:
            - return_type: "raw" | "init-details"
    """
    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'tag:aws:ec2:fleet-id',
                'Values': [
                    fleet_id
                ]
            }
        ]
    )
    with open("response.json", "w") as f:
        print(pretty_json(response), file=f)
    # instance_details = {}
    # for instance in response['Reservations'][0]['Instances']:
    #     instance_details[instance['InstanceId']] = {}
    # instance_ids = [instance['InstanceId'] for instance in response['Reservations'][0]['Instances']]

    if return_type == "raw":
        return extract_instance_details_from_describe_instances_response(response) # quite a complex dict, may need to prune out useless information later
    else: 
        excluded_instances = get_excluded_terminate_instances()
        # response['Reservations'][0]['Instances'][0]['InstanceId']
        return extract_init_details_from_describe_instances_response(response, excluded_instances)

# def get_all_active_spot_fleet_requests(ec2):
#     response = ec2.describe_spot_fleet_requests()
#     print(response)
#     # Filter for active (running) spot fleet requests
#     active_fleet_requests = [fleet['SpotFleetRequestId'] 
#                             for fleet in response['SpotFleetRequestConfigs'] 
#                             if fleet['SpotFleetRequestState'] in ['active', 'modifying']]
#     return active_fleet_requests

def start_instances(ec2, instance_ids):
    response = ec2.start_instances(
        InstanceIds=instance_ids
    )
    return response

def stop_instances(ec2, instance_ids):
    response = ec2.stop_instances(
        InstanceIds=instance_ids
    )
    return response

def reboot_instances(ec2, instance_ids):
    response = ec2.reboot_instances(
        InstanceIds=instance_ids
    )
    return response

def terminate_instances(ec2, instance_ids):
    response = ec2.terminate_instances(
        InstanceIds=instance_ids
    )
    return response

def nuke_all_instances(ec2, excluded_instance_ids):
    """
        Terminates all instances, and spot requests except for the ones specified in excluded_instance_ids
    """
    instances = get_all_running_instances(ec2)
    instances_to_terminate = []
    for instance in instances:
        if instance not in excluded_instance_ids:
            # print(instance)
            instances_to_terminate.append(instance)
    if len(instances_to_terminate) > 300:
        # We can only terminate 300 instances at a time (I believe..)
        for chunk in chunks(instances_to_terminate, 300):
            response = terminate_instances(ec2, chunk)
            print(response)
    else:
        response = terminate_instances(ec2, instances_to_terminate)
        print(response)
    # response = terminate_instances(ec2, instances_to_terminate)
    # print(response)

    # print(get_all_active_spot_fleet_requests(ec2))
    # response = ec2.cancel_spot_fleet_requests(
    #     SpotFleetRequestIds=get_all_active_spot_fleet_requests(ec2),
    #     TerminateInstances=True
    # )

    return instances_to_terminate

def create_fleet(ec2, instance_type, region, launch_template, num):
    print("creating " + instance_type + " fleet with " + str(num) + " instances in region " + region)
    response = ec2.create_fleet(
        SpotOptions={
            'AllocationStrategy': 'lowestPrice',
        },
        LaunchTemplateConfigs=[
            {
                'LaunchTemplateSpecification': {
                    'LaunchTemplateId': launch_template,
                    'Version': '$Default'
                },
                'Overrides': [
                    {
                        'InstanceType': instance_type,
                        'AvailabilityZone': region
                    }
                ]
            }
        ],
        TargetCapacitySpecification={
            'TotalTargetCapacity': num,
            'OnDemandTargetCapacity': 0,
            'SpotTargetCapacity': num,
            'DefaultTargetCapacityType': 'spot'
        },
        Type='request',
        # TagSpecifications=[
        #     {
        #         'Tags': [
        #             {
        #                 'Key': 'fleet-id',
        #                 'Value': fleet_id_tag # this is a string
        #             },
        #         ]
        #     },
        # ],
    )
    return response

def create_nics(ec2, instanceID, nic_count, az):
    """
        Creates the specified number of NICs for a given instance (based on its type) and attaches the NICs to this instance. 

        NOTE: assumes the instance currently only has the default original NIC attached, i.e., only one NIC. 

        Parameters:
            nic_count: NICs to create for this instance
        Returns: 
            - list of nic_ids that were created and attached to this instance
    """
    # Get subnet associated with this availability zone:
    response = ec2.describe_subnets(
        Filters=[
            {
                'Name': 'availabilityZone',
                'Values': [
                    az,
                ]
            },
        ],
    )
    subnet_id = response['Subnets'][0]['SubnetId']

    nic_ids = []

    for i in range(nic_count):
        response = ec2.create_network_interface(SubnetId=subnet_id)
        nic_ids.append(response['NetworkInterface']['NetworkInterfaceId'])

    device_index = 1
    for nic_id in nic_ids:
        response = ec2.attach_network_interface(
            NetworkInterfaceId=nic_id,
            InstanceId=instanceID,
            DeviceIndex=device_index
        )
        device_index += 1
    return nic_ids 

def get_cost(ce, StartTime, EndTime):
    response = ce.get_cost_and_usage(
        TimePeriod={
            'Start': StartTime,
            'End': EndTime
        },
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[
            {
                'Type': 'DIMENSION',
                'Key': 'SERVICE'
            },
        ]
    )
    return response

def get_addresses(ec2):
    response = ec2.describe_addresses()
    return response

def get_public_ip_address(ec2, eip_id):
    response = ec2.describe_addresses(
        AllocationIds=[
            eip_id,
        ]
    )
    return response['Addresses'][0]['PublicIp']

def allocate_address(ec2):
    response = ec2.allocate_address(
        Domain='vpc'
    )
    return response

def get_eip_id_from_allocation_response(response):
    """
        Returns the EIP ID from the response of allocate_address
    """
    return response['AllocationId']

def release_address(ec2, allocation_id):
    response = ec2.release_address(
        AllocationId=allocation_id
    )
    return response

def associate_address(ec2, instance_id, allocation_id, network_interface_id):
    response = ec2.associate_address(
        # InstanceId=instance_id,
        AllocationId=allocation_id,
        NetworkInterfaceId=network_interface_id
    )
    return response

def get_association_id_from_association_response(response):
    return response['AssociationId']

def disassociate_address(ec2, association_id):
    response = ec2.disassociate_address(
        AssociationId=association_id
    )
    return response    

def assign_name_tags(ec2, resource_id, name):
    response = ec2.create_tags(
        Resources=[
            resource_id # resource could be an instance, network interface, eip, etc.
        ],
        Tags=[
            {
                'Key': 'Name',
                'Value': name
            }
        ]
    )
    return response

def ping(ip, backoff_time, trials):
    """
        Parameters:
            ip: string
            backoff_time: int # seconds
            trials: int
        Returns:
            True if ping is successful, False otherwise
    """
    for i in range(trials):
        response = os.system("ping -c 1 " + ip)
        if response == 0:
            return 0
        else:
            time.sleep(backoff_time)
    return 1

def ping_instances(ec2, nic_list, multi_NIC=True, not_fixed=True):
    """
        Checks if instances are pingable.

        Parameters:
            nic_list: list of NIC IDs
            not_fixed: True | False
                - True: # TODO Minor quirk that will be removed later: only the default NIC (i.e., original_nic) is configured to accept pings for now. We will need to fix this later. Will remove this parameter altogether once fixed. 
    """
    failed_ips = []

    # Retry details:
    backoff_time = 10 # seconds
    trials = 3

    # time.sleep(wait_time)
    if not_fixed: # only ping the original NIC
        nic_details = nic_list[-1] # this is the position of the original_nic, since we append it last..
        ip = nic_details[-1]
        response = ping(ip, backoff_time, trials)
        if response == 0:
            print(f"{ip} is up!")
        else:
            print(f"{ip} is down!")
            # if ping fails, add to failed_ips
            failed_ips.append(ip)
    else: # ping all NICs
        for nic_details in nic_list:
            ip = nic_details[-1]
            response = ping(ip, backoff_time, trials)
            if response == 0:
                print(f"{ip} is up!")
            else:
                print(f"{ip} is down!")
                # if ping fails, add to failed_ips
                failed_ips.append(ip)
    return failed_ips
 
def use_jinyu_launch_templates(ec2, instance_type):
    instance_info = get_instance_type(ec2, [instance_type])
    arch = instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures'][0]
    #x86: lt-04d9c8ac5d00a2078
    #arm: lt-0abc44b6c12879596
    if arch == 'arm64':
        launch_template = 'lt-0abc44b6c12879596'
    else:
        launch_template = 'lt-04d9c8ac5d00a2078'
    return launch_template

def use_UM_launch_templates(ec2, region, proxy_impl, type="main"):
    """
        Note: unlike use_jinyu_launch_templates, we currently only support x86_64 for the UM account
        Note: we only use hard-coded values for now since there are only a few for now..

        Parameters:
            - proxy_impl: the only difference for now is the initialization script within the launch template
    """
    if region == "us-east-1":
        if proxy_impl == "wireguard":
            if type == "main": # Sina specific for migration efficacy test
                launch_template_wireguard = "lt-0bd60ca5ce983af4d" # not working yet
            elif type == "side": # Sina specific for migration efficacy test
                launch_template_wireguard = "lt-0e9b68603a74b345b"
            elif type == "peer": # Sina specific for migration efficacy test
                launch_template_wireguard = "lt-0fefbd231bf2265e9"
            else:
                raise Exception("Invalid type: " + type)
            launch_template = launch_template_wireguard 
        elif proxy_impl == "baseline": # not an actual proxy impl
            launch_template_baseline_working = "lt-07c37429821503fca"
            launch_template = launch_template_baseline_working
    elif region == "us-east-2": # Once supported, make similar to the us-east-1 case..
        launch_template = 'NOT-SUPPORTED-YET'
    return launch_template


def use_ragob_launch_templates(ec2, instance_type):
    instance_info = get_instance_type(ec2, [instance_type])
    arch = instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures'][0]
    match arch:
        case "arm64":
            return "lt-038be829389419555"
        case "x86_64":
            return "lt-053f9aacf4be60b60"
        case _:
            return f"unsupported architecture: {arch}"


def print_create_fleet_response(ec2, response):
    print(response['FleetId'])
    all_instance_details = get_specific_instances_with_fleet_id_tag(ec2, response['FleetId']) 
    print(all_instance_details)

def create_initial_fleet_and_periodic_rejuvenation_thread(ec2, input_args, quick_test=False):

    # Extract required input args:
    REJUVENATION_PERIOD = int(input_args['REJUVENATION_PERIOD']) # in seconds
    regions = input_args['regions']
    PROXY_COUNT = int(input_args['PROXY_COUNT']) # aka fleet size 
    PROXY_IMPL = input_args['PROXY_IMPL'] # wireguard | snowflake
    batch_size = input_args['batch_size'] # number of instances to create per thread. Currently, we assume this is completely divisible by PROXY_COUNT.
    MIN_COST = float(input_args['MIN_COST'])
    MAX_COST = float(input_args['MAX_COST'])
    MIN_VCPU = int(input_args['MIN_VCPU']) # not used for now
    MAX_VCPU = int(input_args['MAX_VCPU']) # not used for now
    INITIAL_EXPERIMENT_INDEX = int(input_args['INITIAL_EXPERIMENT_INDEX'])
    multi_nic = input_args['multi_NIC'] # boolean
    mode = input_args['mode'] # liveip | instance 
    data_dir = input_args['dir'] # used for placing the logs.
    wait_time_after_create = input_args['wait_time_after_create'] # e.g., 30
    wait_time_after_nic = input_args['wait_time_after_nic'] # e.g., 30

    filter = {
        "min_cost": MIN_COST, #0.002 for first round of exps..
        "max_cost": MAX_COST,
        "regions": regions
    }

    launch_templates = []

    if PROXY_IMPL in {'snowflake', 'wireguard', 'v2ray'}:
        # launch_templates.extend([input_args['launch-template-main'], input_args['launch-template-side'], input_args['launch-template-peer']]) # main: is the first (and is a single) proxy to connect to, and peer is a client. side is the rest of the proxies. TODO: add creation of a single main and peer later here in this script. 
        launch_templates.append(input_args['launch-template'])
    else:
        raise Exception("Invalid proxy implementation: " + PROXY_IMPL)  

    # # Get cheapest instance:
    # prices = update_spot_prices(ec2)
    # prices = prices.sort_values(by=['SpotPrice'], ascending=True)
    # # print(prices.iloc[0])
    # index, cheapest_instance = get_instance_row_with_supported_architecture_and_regions(ec2, prices, regions=regions)
    # instance_type = cheapest_instance['InstanceType']
    # zone = cheapest_instance['AvailabilityZone']
    
    # Create fleet by batch:
    batch_count = math.ceil(PROXY_COUNT/batch_size)
    initial_region = "us-east-1" # used for initialization purposes
    threads = []
    for i in range(batch_count):
        if mode == "instance":
            tag_prefix = "instance-exp{}-{}fleet-{}mincost".format(str(INITIAL_EXPERIMENT_INDEX), str(PROXY_COUNT), str(filter['min_cost']))
            filename = data_dir + tag_prefix + "-batch-count-{}".format(i) + ".txt"
            file = open(filename, 'w+')
            rejuvenator = rejuvenation.InstanceRejuvenator(initial_region, launch_templates, input_args, filter, tag_prefix, filename)
            
        elif mode == "liveip":
            tag_prefix = "liveip-exp{}-{}fleet-{}mincost".format(str(INITIAL_EXPERIMENT_INDEX), str(PROXY_COUNT), str(filter['min_cost']))
            filename = data_dir + tag_prefix + "-batch-count-{}".format(i) + ".txt"
            file = open(filename, 'w+')
            # live_ip_rejuvenation(initial_ec2, is_UM, REJUVENATION_PERIOD, PROXY_COUNT, EXPERIMENT_DURATION, PROXY_IMPL, filter=filter, tag_prefix=tag_prefix, wait_time_after_create=wait_time_after_create, print_filename=filename)
            rejuvenator = rejuvenation.LiveIPRejuvenator(initial_region, launch_templates, input_args, filter, tag_prefix, filename)

        thread = threading.Thread(target=rejuvenator.rejuvenate, kwargs={
            "quick_test": quick_test
        })
        thread.start()
        threads.append(thread)

    return threads

class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, ec2, input_args, *args, **kwargs):
        self.ec2 = ec2
        super().__init__(*args, **kwargs)

    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('/')[1:]
        print(path)
        match path[0]:
            case 'getNum':
                instances = get_all_instances(self.ec2)
                num = len(instances)
                self._set_response()
                self.wfile.write(str(num).encode('utf-8'))
            case 'interrupt':
                id = path[1]
                response = terminate_instances(self.ec2, [id])
                launch_template = use_jinyu_launch_templates(self.ec2, current_type)
                create_fleet(self.ec2, current_type, region, launch_template, 1)
                self._set_response()
                self.wfile.write(response.encode('utf-8'))
                #notices controller to interrupt instance, WIREGUARD ONLY
            case "getInitDetails":
                # print("Enter getInitDetails")
                instances_details = get_all_instances_init_details(self.ec2)
                self._set_response()
                self.wfile.write(pretty_json(instances_details).encode('utf-8'))
            case "createWireguardMain": # hardcoded. only for the convenience of artifact evaluation.
                response = create_fleet(self.ec2, "m7a.large", "us-east-1", input_args["launch-template-main"], 1)
                self._set_response()
                self.wfile.write(response.encode('utf-8'))
                # TODO: respond to controller..
            case "createWireguardClient": # hardcoded. only for the convenience of artifact evaluation. 
                # print("Enter createClient")
                response = create_fleet(self.ec2, "m7a.medium", "us-east-1", input_args["launch-template-peer"], 1) 
                self._set_response()
                self.wfile.write(response.encode('utf-8'))
            # case "createSnowflakeClient": # TODO: uncomment later. not working yet. Probably need to figure out how to do this with Jinyu separately
            #     # print("Enter createClient")
            #     response = create_fleet(self.ec2, "m7a.medium", "us-east-1", input_args["launch-template-peer"], 1) 
            #     self._set_response()
            #     self.wfile.write(response.encode('utf-8'))
            # case "createNAT": # TODO: uncomment later. not working yet. Probably need to figure out how to do this with Sina and Jinyu separately
            #     # print("Enter createNAT")
            #     response = create_fleet(self.ec2, current_type, region, launch_template, 1)
            #     self._set_response()
            #     self.wfile.write(response.encode('utf-8'))

def run_server(ec2):
    server_address = ('', 8000)
    # https://stackoverflow.com/questions/21631799/how-can-i-pass-parameters-to-a-requesthandler
    handler = partial(RequestHandler, ec2)
    httpd = HTTPServer(server_address, handler)
    print('Starting server...')
    httpd.serve_forever()

def get_cheapest_instance_types_df(ec2, filter=None, multi_NIC=False):
    """
        Parameters:
            multi_NIC == True, used for liveIP and optimal 
            filter: price filter and region filter for now
                Format: {
                    "min_cost": float,
                    "max_cost": float,
                    "regions": ["us-east-1", ...], # list of regions to include in the creation process. Note: make sure a suitable launch template exists for each region listed
                    }

        df format:
        spot_prices.append({
            'AvailabilityZone': response['AvailabilityZone'],
            'InstanceType': response['InstanceType'],
            'MaximumNetworkInterfaces': type_to_NIC[response['InstanceType']],
            'SpotPrice': response['SpotPrice'],
            'PricePerInterface': (float(response['SpotPrice']) + 0.005 * (type_to_NIC[response['InstanceType']] - 1)) / type_to_NIC[response['InstanceType']],
            'Timestamp': response['Timestamp']  
        })

        returns the entire df sorted accordingly
    """

    # Look into cost catalogue and sort based on multi_NIC or not:
    prices = update_spot_prices(ec2) # AWS prices
    
    # Get sorted prices:
    if multi_NIC:
        prices = prices.sort_values(by=['PricePerInterface'], ascending=True)
    else:
        prices = prices.sort_values(by=['SpotPrice'], ascending=True)

    # Filter based on min_cost and max_cost, if filter exists:
    if isinstance(filter, dict):
        min_cost = filter['min_cost']
        max_cost = filter['max_cost']
        regions = filter['regions']
        if regions:
            # Only keep rows where AvailabilityZone contains one of the values in the regions list:
            prices = prices[prices['AvailabilityZone'].str.startswith(tuple(regions))] # https://stackoverflow.com/a/20461857/13336187
        if min_cost:
            if multi_NIC:
                prices = prices[prices['PricePerInterface'] >= min_cost]
            else:
                # print(prices.dtypes)
                # print(isinstance(prices['PricePerInterface'], float))
                # print(isinstance(min_cost, float))
                prices = prices[prices['SpotPrice'] >= min_cost]
        if max_cost:
            if multi_NIC:
                prices = prices[prices['PricePerInterface'] <= max_cost]
            else:
                prices = prices[prices['SpotPrice'] <= max_cost]

    return prices

def get_instance_row_with_supported_architecture(ec2, prices, supported_architecture=['x86_64']):
    """
        Copied from rejuvenation-eval-script.py
        Parameters:
            supported_architecture: list of architectures to support. Default is x86_64 (i.e., Intel/AMD)
            prices: df of prices (from get_cheapest_instance_types_df)
        Returns:
            row of the cheapest instance type that supports the architecture
    """
    for index, row in prices.iterrows():
        instance_type = row['InstanceType']
        instance_info = get_instance_type(ec2, [instance_type])
        for arch in instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures']:
            if arch in supported_architecture:
                return index, row
        # if instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures'][0] in supported_architecture:
        #     return index, row
    raise Exception("No instance type supports the architecture: " + str(supported_architecture))

# example usage of creating 2 instances in us-east-1 with UM account: python3 api.py UM us-east-1 2 main
# explanation of above example: this creates 2 instances in the us-east-1a az, in the UM AWS account
if __name__ == '__main__':
    input_args_filename = sys.argv[1]
    input_args = parse_input_args(input_args_filename)

    if len(sys.argv) > 2:
        if sys.argv[2] == "simple-test":
            ec2, ce = choose_session(region=region)
            threads = create_initial_fleet_and_periodic_rejuvenation_thread(ec2, input_args, quick_test=True)
        else:
            # Exit script, invalid argument:
            print("Invalid argument: " + sys.argv[2])
            sys.exit(1)
    else:
        ec2, ce = choose_session(region=region)
        threads = create_initial_fleet_and_periodic_rejuvenation_thread(ec2, input_args)

        run_server(ec2)

    time.sleep(10) # wait for threads to start

    for thread in threads:
        # Wait for threads to end:
        thread.join()

    # Some example usage from Patrick:
    """
    response = get_all_instances()

    # Create two instances: 
    UM_launch_template_id = "lt-07c37429821503fca"
    response = create_fleet("t2.micro", "us-east-1c", UM_launch_template_id, 2) # verified working (USE THIS)

    response = create_fleet2("t2.micro", "us-east-1c", UM_launch_template_id, 2) # not working yet

    print(response)

    # Delete instances using the fleet-id key returned from the response above:

    instance_ids = get_specific_instances_with_fleet_id_tag('fleet-4da19c85-1000-4883-a480-c0b7a34b444b')
    print(instance_ids)
    for i in instance_ids:
        response = terminate_instances([i])
        print(response)
    """