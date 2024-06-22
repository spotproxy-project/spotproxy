import pandas as pd
# import modin.pandas as pd
import dateutil
import calendar
from collections import defaultdict
import sys

from os import listdir
from os.path import isfile, join

def get_all_files_in_dir(mypath):
    return [join(mypath, f) for f in listdir(mypath) if isfile(join(mypath, f))]

def pretty_json(obj, filename=None):
    if filename:
        with open(filename, 'w') as f:
            f.write(json.dumps(obj, sort_keys=True, indent=4, default=str))
    else:
        return json.dumps(obj, sort_keys=True, indent=4, default=str)

import boto3
import json
from pkg_resources import resource_filename

# SECTION: get on-demand pricing of ec2 instance type: 
# Copied from: https://stackoverflow.com/a/51685222/13336187

# Search product filter. This will reduce the amount of data returned by the
# get_products function of the Pricing API
FLT = '[{{"Field": "tenancy", "Value": "shared", "Type": "TERM_MATCH"}},'\
      '{{"Field": "operatingSystem", "Value": "{o}", "Type": "TERM_MATCH"}},'\
      '{{"Field": "preInstalledSw", "Value": "NA", "Type": "TERM_MATCH"}},'\
      '{{"Field": "instanceType", "Value": "{t}", "Type": "TERM_MATCH"}},'\
      '{{"Field": "location", "Value": "{r}", "Type": "TERM_MATCH"}},'\
      '{{"Field": "capacitystatus", "Value": "Used", "Type": "TERM_MATCH"}}]'


# Get current AWS price for an on-demand instance
def get_price(region, instance, os):
    f = FLT.format(r=region, t=instance, o=os)
    data = client.get_products(ServiceCode='AmazonEC2', Filters=json.loads(f))
    od = json.loads(data['PriceList'][0])['terms']['OnDemand']
    id1 = list(od)[0]
    id2 = list(od[id1]['priceDimensions'])[0]
    return od[id1]['priceDimensions'][id2]['pricePerUnit']['USD']

# Translate region code to region name. Even though the API data contains
# regionCode field, it will not return accurate data. However using the location
# field will, but then we need to translate the region code into a region name.
# You could skip this by using the region names in your code directly, but most
# other APIs are using the region code.
def get_region_name(region_code):
    default_region = 'US East (N. Virginia)'
    endpoint_file = resource_filename('botocore', 'data/endpoints.json')
    try:
        with open(endpoint_file, 'r') as f:
            data = json.load(f)
        # Botocore is using Europe while Pricing API using EU...sigh...
        return data['partitions'][0]['regions'][region_code]['description'].replace('Europe', 'EU')
    except IOError:
        return default_region

def get_instance_type(ec2, types):
    response = ec2.describe_instance_types(
        InstanceTypes=types
    )
    return response

def get_instance_row_with_supported_architecture(ec2, instance_type_list, supported_architecture=['x86_64']):
    """
        Copied from rejuvenation-eval-script.py
        Parameters:
            supported_architecture: list of architectures to support. Default is x86_64 (i.e., Intel/AMD)
            instance_type_list: list of instance types to check for supported architecture
        Returns:
            row of the cheapest instance type that supports the architecture
    """
    supported_instance_types = []
    for instance_type in instance_type_list:
        try:
            instance_info = get_instance_type(ec2, [instance_type])
        except Exception as e:
            print(e)
            continue
        for arch in instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures']:
            if arch in supported_architecture:
                supported_instance_types.append(instance_info['InstanceTypes'][0]['InstanceType'])
        # if instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures'][0] in supported_architecture:
        #     return index, row
    return supported_instance_types

#parameter date is the string I receive on the POST
def validate(date):
    try:
        dateutil.parser.parse(date)
        # a valid date would be 20220509T000000Z
        return True
    except Exception as e:
        # an incorrect date would be 2022509T000000Z
        return 'Error, incorrect date values'

print(validate('2023-10-01T00:00:00+00:00'))

def calculate_cost(ec2, df, end_date='2023-12-31T23:59:59+00:00', start_date='2023-12-01T00:00:00+00:00', multi_nic=False):
    total_cost = 0
    total_seconds_elapsed = 0
    cost_arbitrage_intervals = []

    instance_types_response = ec2.describe_instance_types(
        InstanceTypes=[df.iloc[0]['instance-type']]
    )
    #add instance types to spot price history
    max_nics = instance_types_response['InstanceTypes'][0]['NetworkInfo']['MaximumNetworkInterfaces']
    
    if multi_nic:
        price_prev = df.iloc[0]['price'] / max_nics
        nic_price_prev = 0.005 
    else:
        price_prev = df.iloc[0]['price']
        nic_price_prev = 0.005 
    datetime_prev = df.iloc[0]['datetime']
    for index, row in enumerate(df.itertuples(), 1):    
        aws_zone = 1
        instance_type = 2
        price = 4
        index = 0
        datetime_index = 5

        seconds_elapsed = (row[datetime_index]-datetime_prev).total_seconds() # since billing is generally per second
        cost_arbitrage_intervals.append(seconds_elapsed)
        # print(seconds_elapsed, row[datetime_index], datetime_prev)
        # while True:
        #     a =1
        total_cost += (price_prev+nic_price_prev)/60/60 * seconds_elapsed
        total_seconds_elapsed += seconds_elapsed
        if multi_nic:
            price_prev = row[price] / max_nics
            nic_price_prev = 0.005 
        else:
            price_prev = row[price]
            nic_price_prev = 0.005 
        datetime_prev = row[datetime_index]
    
    # Calculate cost for the remainder of the month:
    seconds_elapsed = (dateutil.parser.parse(end_date)-datetime_prev).total_seconds() # since billing is generally per second
    # print(seconds_elapsed, dateutil.parser.parse(end_date),datetime_prev)
    total_cost += (price_prev+nic_price_prev)/60/60 * seconds_elapsed
    total_seconds_elapsed += seconds_elapsed
    print("Total seconds elapsed: ", total_seconds_elapsed)
    print("Correct total seconds elapsed: ", (dateutil.parser.parse(end_date)-dateutil.parser.parse(start_date)).total_seconds())
    assert total_seconds_elapsed == (dateutil.parser.parse(end_date)-dateutil.parser.parse(start_date)).total_seconds()
    # Note: some potential links and an incomplete code snippet to automate this:
    # https://stackoverflow.com/questions/26105804/extract-month-from-date-in-python
    # https://stackoverflow.com/questions/9481136/how-to-find-number-of-days-in-the-current-month
    """
        from datetime import datetime, timedelta

        # Your given datetime string
        datetime_str = '2023-12-01 00:00:00+00:00'

        # Convert the string to a datetime object
        datetime_obj = datetime.fromisoformat(datetime_str)

        # Getting the first day of the next month
        first_day_next_month = datetime_obj.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=31)
        first_day_next_month = first_day_next_month.replace(day=1)

        # Subtracting one second to get the last second of the current month
        last_second_current_month = first_day_next_month - timedelta(seconds=1)

        last_second_current_month.isoformat()
    """

    return total_cost, cost_arbitrage_intervals

def extract_month_year_from_filename(filename):
    """
        Filename format: ../../aws-spot-price-history/prices/2022/01.tsv
    """
    month = filename.split('/')[-1].split('.')[0]
    # month = filename.split('.')[0]
    year = filename.split('/')[-2]
    return month, year

def get_aws_format_region(zone):
    """
        Convert use2 to us-east-2. Convert euw1 to eu-west-1. Convert apse2 to ap-southeast-2. And so on.

        Possible values for zone: ['apse2-az2' 'euw2-az3' 'apne2-az3' 'euc1-az3' 'usw2-az2' 'euw1-az2'
                            'sae1-az2' 'cac1-az2' 'aps1-az3' 'usw2-az1' 'apne1-az4' 'mes1-az1'
                            'euw3-az3' 'apse1-az1' 'aps1-az1' 'apne2-az1' 'use1-az1' 'euw1-az3'
                            'euw1-az1' 'use2-az3' 'euc1-az2' 'euc1-az1' 'apne1-az1' 'usw1-az3'
                            'usw1-az1' 'apse1-az2' 'apne1-az2' 'apse2-az3' 'apse2-az1' 'euw3-az2'
                            'euw3-az1' 'eun1-az3' 'eun1-az2' 'eun1-az1' 'apne2-az4' 'apne2-az2'
                            'cac1-az1' 'cac1-az4' 'aps1-az2' 'use2-az2' 'usw2-az3' 'apse1-az3'
                            'euw2-az2' 'use1-az2' 'use1-az6' 'use1-az4' 'ape1-az3' 'ape1-az2'
                            'ape1-az1' 'sae1-az3' 'eus1-az3' 'eus1-az2' 'eus1-az1' 'mes1-az3'
                            'mes1-az2' 'aps2-az3' 'aps2-az2' 'aps2-az1' 'mec1-az3' 'mec1-az2'
                            'mec1-az1' 'use2-az1' 'usw2-az4' 'sae1-az1' 'apse3-az3' 'apse3-az2'
                            'apse3-az1' 'eus2-az1' 'euc2-az3' 'euc2-az2' 'euc2-az1' 'euw2-az1'
                            'afs1-az2' 'apse4-az3' 'apne3-az3' 'eus2-az3' 'eus2-az2' 'apse4-az1'
                            'afs1-az1' 'use1-az5' 'afs1-az3' 'apne3-az2' 'apne3-az1' 'apse4-az2'
                            'use1-az3']
    """
    region = zone.split("-")[0]
    area = ""
    num = 999
    if region[2] == 'e':
        area = "east"
        num = region[3]
    elif region[2] == 'w':
        area = "west"
        num = region[3]
    elif region[2] == 'n':
        if region[3] == 'e':
            area = "northeast"
        elif region[3] == 'w':
            area = "northwest"
        num = region[4]
    elif region[2] == 's':
        if region[3] == 'e':
            area = "southeast"
        elif region[3] == 'w':
            area = "southwest"
        num = region[4]
    elif region[2] == 'c':
        area = "central"
        num = region[3]

    region = region[0:2] + "-" + area + "-" + num
    
    return region

# SECTION: input data: 
# # December 2023:
# df = pd.read_csv('../../aws-spot-price-history/prices/2023/12.tsv', sep='\t', header=None)
# start_date = '2023-12-01 00:00:00+00:00' # make sure this is aligned with the month of the filename..
# end_date = '2023-12-31 23:59:59+00:00' # make sure this is aligned with the month of the filename..
# November 2023:

if __name__ == '__main__':

    min_cost = float(sys.argv[1]) # 0.051
    max_cost = float(sys.argv[2]) # 0.3

    directory1 = "./aws-spot-price-history/prices/2022/"
    directory2 = "./aws-spot-price-history/prices/2023/"
    directory3 = "./aws-spot-price-history/prices/2024/"

    """
        Format:
            {
                "1, 2022": {
                    data_filename : "../../aws-spot-price-history/prices/2022/01.tsv",
                    start_date : "2022-01-01 00:00:00+00:00",
                    end_date : "2022-01-31 23:59:59+00:00",
                    optimal_single_cost: float, # single NIC utilized cost
                    optimal_multi_cost: float,
                    baseline_static_spotvm_cost: float,
                    baseline_static_normalvm_cost: float,
                    baseline_static_instance_type: str, # both baselines share the same instance type
                    cost_arbitrage_intervals: e.g., [30, 60, 20, 120] # 30 seconds after initilization, the first cost arbitrage event was identified. 60 mins after that another cost arbitrage event was identified... and so on..
                },
                "2, 2022": {...},
                ...
            }
    """
    price_history_details = {} 

    for directory in [directory1, directory2, directory3]:
        all_files = get_all_files_in_dir(directory)
        all_tsv_files = [f for f in all_files if f.endswith(".tsv")] # only get tsv files. Even though pandas can directly process .zst too, but I purposely want to skip 2022/05.tsv.zst since it is invalid.
        for filename in all_tsv_files:
            month, year = extract_month_year_from_filename(filename)
            # if month != "01" or year != "2024":
            #     continue
            start_date = year + "-" + month + "-01 00:00:00+00:00"
            end_date = year + "-" + month + "-" + str(calendar.monthrange(int(year), int(month))[1]) + " 23:59:59+00:00"
            price_history_details[month + ", " + year] = {'data_filename': filename, 'start_date': start_date, 'end_date': end_date}

            df = pd.read_csv(filename, sep='\t', header=None)
            # Add headers to df:
            df.columns = ['aws-zone', 'instance-type', 'distribution', 'price', 'datetime']
            print(df.head())
            # Print all unique values for aws-zone:
            print(df['aws-zone'].unique())
            # print(df['instance-type'].unique())
            

            # Commenting out to save time. This is just to get the cheapest instance type that supports the architecture:
            # my_session = boto3.session.Session(profile_name='spotproxy-pat-umich-role')
            # ec2 = my_session.client('ec2', 'us-east-1')
            # supported_arch_instance_types = get_instance_row_with_supported_architecture(ec2, df['instance-type'].unique().tolist())
            # print(supported_arch_instance_types)
            supported_arch_instance_types = ['g4dn.4xlarge', 'inf1.xlarge', 'r6i.2xlarge', 't2.large', 'm5.24xlarge', 'r5a.xlarge', 'c6i.large', 'r6i.xlarge', 'c5.xlarge', 'c5.9xlarge', 'm5d.4xlarge', 'i3en.24xlarge', 'm5zn.6xlarge', 't3a.large', 'c5d.metal', 'r5n.metal', 'c5n.large', 'r5.24xlarge', 'm3.large', 'm5ad.16xlarge', 'd2.8xlarge', 'g4ad.4xlarge', 'inf1.6xlarge', 'm5a.8xlarge', 'i3en.6xlarge', 'd2.4xlarge', 'x1e.xlarge', 'r5a.2xlarge', 't3a.micro', 'i3.2xlarge', 'm6i.32xlarge', 'r5d.2xlarge', 'g4dn.2xlarge', 'g4dn.xlarge', 'r5dn.12xlarge', 'c5.12xlarge', 'r5.2xlarge', 'r4.4xlarge', 'r5d.8xlarge', 'r5d.4xlarge', 'c5n.4xlarge', 'g4dn.16xlarge', 'r5d.xlarge', 'r5n.2xlarge', 'i3.16xlarge', 'm5a.4xlarge', 'r5b.24xlarge', 'c5.2xlarge', 'm5.2xlarge', 'm6i.2xlarge', 'c6a.24xlarge', 'm5ad.4xlarge', 'r5d.24xlarge', 'g3.4xlarge', 'm5.large', 'm5d.2xlarge', 'c5a.16xlarge', 'r5b.4xlarge', 'm5.12xlarge', 'm5d.12xlarge', 'r5.12xlarge', 'x2iedn.4xlarge', 'x2iedn.8xlarge', 'm5a.large', 'r5a.12xlarge', 'm6i.xlarge', 'i2.xlarge', 'm5a.xlarge', 'm6i.4xlarge', 'g4dn.12xlarge', 'r3.4xlarge', 'r5.8xlarge', 'c5n.18xlarge', 'm5ad.8xlarge', 'm5n.4xlarge', 'm5n.12xlarge', 'p2.16xlarge', 'r5dn.4xlarge', 'm6i.large', 'm5dn.2xlarge', 'c5d.9xlarge', 'm5dn.8xlarge', 'r5ad.16xlarge', 'm5.metal', 'r4.8xlarge', 'f1.4xlarge', 'c5d.18xlarge', 'c5a.24xlarge', 'inf1.24xlarge', 'm4.4xlarge', 'c4.large', 'c6i.4xlarge', 'r5b.12xlarge', 'm5d.metal', 'c3.2xlarge', 'm5n.2xlarge', 'm5d.xlarge', 'c5n.xlarge', 'c6a.4xlarge', 'm6i.8xlarge', 'r5d.large', 'r5n.24xlarge', 'inf1.2xlarge', 'r6i.metal', 'm5.4xlarge', 'r5b.2xlarge', 'r5n.16xlarge', 'i3en.2xlarge', 'c4.8xlarge', 'x1.16xlarge', 'c5n.2xlarge', 'r5b.large', 'p3.2xlarge', 'm5a.2xlarge', 'm5a.24xlarge', 'm6a.xlarge', 'c6i.metal', 'i4i.xlarge', 'r5b.16xlarge', 'c1.xlarge', 'i4i.16xlarge', 'i3en.3xlarge', 'c4.xlarge', 'm6i.24xlarge', 'r4.2xlarge', 'm6a.4xlarge', 'c5a.8xlarge', 'm5.8xlarge', 't3.xlarge', 'r5a.8xlarge', 'm6a.12xlarge', 'r5ad.4xlarge', 'm4.16xlarge', 'c6i.8xlarge', 'm5d.8xlarge', 'm5ad.xlarge', 'm6id.4xlarge', 'c5a.4xlarge', 'm3.2xlarge', 'r5.metal', 'r5ad.2xlarge', 'm5a.12xlarge', 'r5ad.8xlarge', 'm4.large', 'c5ad.xlarge', 'i2.4xlarge', 'c5ad.12xlarge', 't3a.small', 'm5n.large', 'r5n.8xlarge', 'm5ad.large', 'm5d.16xlarge', 'r5a.16xlarge', 'r5dn.16xlarge', 'c5d.24xlarge', 'c5ad.8xlarge', 'c4.4xlarge', 'm5ad.12xlarge', 'r5.4xlarge', 'm5n.16xlarge', 'r6i.8xlarge', 'c5.metal', 'r3.large', 'c5d.12xlarge', 'm5dn.24xlarge', 'c5.24xlarge', 'm5n.xlarge', 'm6id.metal', 'm4.10xlarge', 'r5.16xlarge', 'c5.18xlarge', 'r5.large', 'r5ad.24xlarge', 'c5.large', 'g4ad.16xlarge', 'm5.xlarge', 't3a.xlarge', 'm5a.16xlarge', 'r5b.xlarge', 'c5d.4xlarge', 'm5ad.2xlarge', 'c6i.12xlarge', 'g4ad.2xlarge', 'c6id.large', 'r4.xlarge', 'm4.2xlarge', 'i2.8xlarge', 'c4.2xlarge', 'r5.xlarge', 'i3.xlarge', 'm5d.large', 'g4ad.xlarge', 'm4.xlarge', 'r5a.4xlarge', 'g5.12xlarge', 'r6i.12xlarge', 'r4.16xlarge', 'p3.16xlarge', 'd2.2xlarge', 'r6i.24xlarge', 'c5d.xlarge', 'r6i.4xlarge', 'g5.48xlarge', 'm6id.12xlarge', 'c5n.9xlarge', 'g4dn.8xlarge', 'r3.8xlarge', 'c5a.2xlarge', 'm5zn.12xlarge', 'r5dn.2xlarge', 'r5dn.xlarge', 'h1.8xlarge', 'm5zn.2xlarge', 'r5dn.8xlarge', 'c6i.32xlarge', 'c5d.2xlarge', 'm5n.8xlarge', 'r5n.12xlarge', 't2.2xlarge', 'm5dn.4xlarge', 'g4dn.metal', 'm5dn.metal', 'z1d.3xlarge', 'c5n.metal', 't3a.2xlarge', 'r4.large', 'm5n.24xlarge', 'r5ad.12xlarge', 'c6i.xlarge', 'c3.8xlarge', 'x1e.2xlarge', 'g3.8xlarge', 't3.large', 'm5d.24xlarge', 'c6a.2xlarge', 'i3.4xlarge', 'c6i.2xlarge', 'r5n.4xlarge', 'm5zn.xlarge', 'm5zn.metal', 'c6id.24xlarge', 'r5a.24xlarge', 'c6i.16xlarge', 'r6i.32xlarge', 'c6i.24xlarge', 'm6a.8xlarge', 'r5n.xlarge', 'c5a.12xlarge', 'm5.16xlarge', 'm6i.16xlarge', 'p2.8xlarge', 'r5b.8xlarge', 'r5a.large', 'r6i.16xlarge', 'r5d.16xlarge', 'r5d.12xlarge', 'm2.4xlarge', 'p3.8xlarge', 'c3.4xlarge', 'i3en.metal', 'm5dn.xlarge', 'r5ad.xlarge', 'x2iedn.24xlarge', 'g5.xlarge', 'vt1.24xlarge', 'x2iedn.metal', 'c3.xlarge', 'c5ad.4xlarge', 'vt1.6xlarge', 'x2idn.16xlarge', 'vt1.3xlarge', 'z1d.metal', 'm1.large', 'm3.xlarge', 'i2.2xlarge', 'g3s.xlarge', 'c6a.8xlarge', 'h1.16xlarge', 'g5.24xlarge', 'i3.8xlarge', 'c5a.large', 't3.2xlarge', 'm5zn.3xlarge', 'c5a.xlarge', 'd3en.12xlarge', 'h1.4xlarge', 'd3en.4xlarge', 'c6a.32xlarge', 'r5d.metal', 'x2iezn.4xlarge', 'm6a.2xlarge', 'm5dn.large', 'c3.large', 'c5.4xlarge', 'm6i.12xlarge', 'r3.2xlarge', 'c6a.16xlarge', 'd3en.2xlarge', 'x1e.8xlarge', 'r5b.metal', 'c5ad.2xlarge', 'm5ad.24xlarge', 'g4ad.8xlarge', 'm6a.metal', 'm5dn.12xlarge', 'r3.xlarge', 't2.xlarge', 'c6a.12xlarge', 'i3en.12xlarge', 'm6id.2xlarge', 'g5.4xlarge', 'm6id.8xlarge', 'p3dn.24xlarge', 'm6id.32xlarge', 'c6id.8xlarge', 'm6id.xlarge', 'm6id.16xlarge', 'm6id.24xlarge', 'i3.metal', 'p4d.24xlarge', 'm6id.large', 'g5.2xlarge', 't3a.nano', 'm6a.24xlarge', 'x1e.32xlarge', 't3a.medium', 'm1.small', 'x1e.4xlarge', 'i3en.large', 'd3.xlarge', 'i3en.xlarge', 'm5dn.16xlarge', 'dl1.24xlarge', 'g5.16xlarge', 'm6a.16xlarge', 'm3.medium', 'x2iedn.2xlarge', 'z1d.6xlarge', 'r5dn.24xlarge', 'g3.16xlarge', 'p2.xlarge', 'x2iedn.32xlarge', 'm5n.metal', 'r5ad.large', 'g5.8xlarge', 'x1e.16xlarge', 'r5n.large', 'r6i.large', 'd3.2xlarge', 'z1d.12xlarge', 'i3.large', 't2.small', 'c6id.4xlarge', 'c6id.xlarge', 'c6id.2xlarge', 'c6id.16xlarge', 'c6id.metal', 'z1d.2xlarge', 'c6id.32xlarge', 'm6i.metal', 'd3en.8xlarge', 'c5ad.16xlarge', 'm6a.48xlarge', 'x2iedn.16xlarge', 'c6a.48xlarge', 'm6a.large', 'c6id.12xlarge', 'x2idn.metal', 'm5zn.large', 'c5ad.24xlarge', 't1.micro', 't2.micro', 'm1.xlarge', 't3.medium', 'c6a.metal', 'd2.xlarge', 'm2.xlarge', 'm2.2xlarge', 'c6a.xlarge', 'i4i.4xlarge', 't3.nano', 't3.micro', 'c6a.large', 'x2iezn.6xlarge', 'h1.2xlarge', 'x2iedn.xlarge', 'x1.32xlarge', 'c5d.large', 't3.small', 't2.medium', 'd3.4xlarge', 'i4i.32xlarge', 'f1.2xlarge', 'x2idn.32xlarge', 'c1.medium', 'm6a.32xlarge', 'd3.8xlarge', 'z1d.xlarge', 'r5dn.metal', 'm1.medium', 'x2idn.24xlarge', 'c5ad.large', 'f1.16xlarge', 'x2iezn.8xlarge', 'z1d.large', 'r5dn.large', 'd3en.xlarge', 'i4i.2xlarge', 'x2iezn.metal', 'x2iezn.12xlarge', 'i4i.8xlarge', 'i4i.metal', 'x2iezn.2xlarge', 'i4i.large', 'd3en.6xlarge', 'r6id.xlarge', 'r6id.2xlarge', 'r6id.large', 'r6id.4xlarge', 'r6id.12xlarge', 'r6id.8xlarge', 'r6id.16xlarge', 'r6id.24xlarge', 'r6id.32xlarge', 'r6id.metal', 'r6a.12xlarge', 'r6a.48xlarge', 'r6a.xlarge', 'r6a.16xlarge', 'r6a.8xlarge', 'r6a.large', 'r6a.metal', 'r6a.24xlarge', 'r6a.4xlarge', 'r6a.32xlarge', 'r6a.2xlarge', 'trn1.2xlarge', 'trn1.32xlarge', 'r6in.12xlarge', 'r6in.4xlarge', 'r6in.large', 'r6in.xlarge', 'r6in.8xlarge', 'r6idn.16xlarge', 'r6in.32xlarge', 'r6idn.8xlarge', 'r6idn.large', 'r6idn.24xlarge', 'r6in.2xlarge', 'r6idn.32xlarge', 'r6idn.xlarge', 'r6in.16xlarge', 'r6idn.12xlarge', 'r6in.24xlarge', 'r6idn.2xlarge', 'r6idn.4xlarge', 'm6in.12xlarge', 'm6idn.2xlarge', 'm6in.8xlarge', 'm6idn.32xlarge', 'm6idn.large', 'm6idn.24xlarge', 'm6in.xlarge', 'm6idn.4xlarge', 'm6in.large', 'm6idn.16xlarge', 'm6idn.xlarge', 'm6in.16xlarge', 'm6idn.12xlarge', 'm6in.32xlarge', 'm6idn.8xlarge', 'm6in.2xlarge', 'm6in.24xlarge', 'm6in.4xlarge', 'c6in.12xlarge', 'c6in.xlarge', 'c6in.8xlarge', 'c6in.4xlarge', 'c6in.24xlarge', 'c6in.2xlarge', 'c6in.32xlarge', 'c6in.large', 'c6in.16xlarge']


            # # Filter out rows that don't have instance-type == 't2.micro' and distribution == 'Linux/UNIX':
            # df = df[(df['instance-type'] == 't1.micro') & (df['distribution'] == 'Linux/UNIX')]
            # # print(df.index)

            # df['datetime'] = pd.to_datetime(df['datetime']) # convert string to datetime 

            # # SECTION: Group rows according to datetime (per hour) and get the lowest price for each group (per hour):
            # # df = df.groupby(pd.Grouper(key="datetime", freq='H'))['price'].nlargest(3)
            # # df = df.groupby(pd.Grouper(key="datetime", freq='H')).apply(lambda x: x.sort_values(["price"], ascending = True))
            # # df = df.groupby(['aws-zone', pd.Grouper(key="datetime", freq='H')]).apply(lambda x: x.sort_values(["price"], ascending = True))
            # df = df.groupby(pd.Grouper(key="datetime", freq='H')).apply(lambda x: x.nsmallest(1, columns = "price")) # latest

            # # SECTION: get unique aws-zones present in the data:
            # # df = df['aws-zone'].drop_duplicates().sort_values()

            # SECTION: get how often instance price shuffling occurs:
            # Filter out rows that don't have instance-type == 't2.micro' and distribution == 'Linux/UNIX':
            # df = df[(df['instance-type'] == 't1.micro') & (df['distribution'] == 'Linux/UNIX')]
            # print(df.index)

            # Filter out rows that don't have distribution == 'Linux/UNIX':
            df = df[df['distribution'] == 'Linux/UNIX']

            df['datetime'] = pd.to_datetime(df['datetime']) # convert string to datetime 
            # df = df.sort_values(by='datetime') # already sorted according to datetime, skip this
            # df.to_csv('temp.csv', index=False) # backup

            # SECTION: FILTERING:
            # Obsolete filters: 
            # Filter out rows from the previous month:
            # df = df[df['datetime'] != '2023-10-01 00:00:00+00:00']
            
            # Default filters:
            # Only keep us zones:
            df = df[df['aws-zone'].str.startswith('us')]

            # Subjective filters: 
            # Filter out rows where price is what I observed most 2 vCPU normal instances (non-burstable) to be:
            df = df[(df['price'] > min_cost) & (df['price'] < max_cost)]

            # Filter out rows where instance-type is not in the list of supported architectures:
            # df = df[df['instance-type'].isin(supported_arch_instance_types)]

            # # Remove rows where instance-type is t type (e.g., t3):
            df = df[~df['instance-type'].astype(str).str.startswith('t')]

            # # Remove rows where instance-type is c1, a1, m1 type (which are outdated..):
            df = df[~df['instance-type'].astype(str).str.startswith('c1')]
            df = df[~df['instance-type'].astype(str).str.startswith('a1')]
            df = df[~df['instance-type'].astype(str).str.startswith('m1')]
            # df = df[~df['instance-type'].astype(str).str.startswith('m3')]
            # df = df[~df['instance-type'].astype(str).str.startswith('c6g')] # remove these as they are ARM instances.. just testing..
            # df = df[~df['instance-type'].astype(str).str.startswith('is4')]

            # Remove rows that have less than 2 vCPUs and 4GB RAM:
            df = df[~df['instance-type'].astype(str).str.contains('medium')]
            df = df[~df['instance-type'].astype(str).str.contains('small')]
            df = df[~df['instance-type'].astype(str).str.contains('nano')]
            df = df[~df['instance-type'].astype(str).str.contains('micro')]

            #  SECTION: PRE-PROCESSING (getting only cheapest rows):
            # TODO later:
            # aws ec2 describe-instance-types --instance-types a1.medium | jq '.InstanceTypes[0].VCpuInfo.DefaultVCpus'

            df_original = df.copy() # backup
            indices_to_drop = []

            # Format: this shows the current price of each instance type in each zone:
            {
                "usw2-az3": {
                    "t2.micro": 0.01,
                }
            }
            cheapest_rows = defaultdict(lambda: defaultdict(float))

            # Iterate over the DataFrame
            # for index, row in df.iterrows():
            index = 1
            for idx, row in df.iterrows():
                # print(index, row.name)
                # aws_zone = 1
                # instance_type = 2
                # price = 4
                # index_df = 0
                if index == 1:
                    current_cheapest_row = row

                    cheapest_rows[row["aws-zone"]][row["instance-type"]] = row["price"]
                    # print(row)
                    # while True:
                    #     x=1
                else:
                    # Check cheapest_rows to see if the same instance type & aws-zone exists:
                    if row["aws-zone"] in cheapest_rows and row["instance-type"] in cheapest_rows[row["aws-zone"]]:
                        # if current row is cheaper than current cheapest row, then update current cheapest row:
                        # if float(row["price"]) < float(cheapest_rows[row["aws-zone"]][row["instance-type"]]):
                        cheapest_rows[row["aws-zone"]][row["instance-type"]] = row["price"]
                    else: # if the same instance type & aws-zone doesn't exist in cheapest_rows, then add it:
                        cheapest_rows[row["aws-zone"]][row["instance-type"]] = row["price"]
                # print(current_cheapest_row)
                # print(row)
                # Check if the same instance type & aws-zone as the previous row:
                if row["aws-zone"] == current_cheapest_row["aws-zone"] and row["instance-type"] == current_cheapest_row["instance-type"]:
                    lowest_priced_row = {"aws-zone": row["aws-zone"], "instance-type": row["instance-type"], "price": row["price"]}
                    # if there exist a cheaper row in cheapest_rows, use it:
                    for zone, instance_info in cheapest_rows.items():
                        for instance_type_this, price_this in instance_info.items():
                            if float(price_this) < float(lowest_priced_row["price"]):
                                lowest_priced_row = {"aws-zone": zone, "instance-type": instance_type_this, "price": price_this}

                    current_cheapest_row = row
                    # print(current_cheapest_row)
                    
                    # Modify the instance to use: (helpful if a cheaper was found from the past) # NOTE: incorrect distribution is fine, since we've already filtered out those that we don't want to include..
                    # print(df)
                    df.at[idx, "aws-zone"] = lowest_priced_row["aws-zone"]
                    df.at[idx, "instance-type"] = lowest_priced_row["instance-type"]
                    df.at[idx, "price"] = lowest_priced_row["price"]
                    current_cheapest_row = df.loc[idx]
                    # print(current_cheapest_row)

                # if current row is cheaper than current cheapest row, then update current cheapest row:
                elif row["price"] < current_cheapest_row["price"]:
                    current_cheapest_row = row
                # else remove current row:
                else:
                    indices_to_drop.append(idx) 

                index += 1

            # Drop the rows
            # print(indices_to_drop[0])
            df.drop(indices_to_drop, inplace=True)
            df.to_csv('temp.csv', index=False) # backup

            # SECTION: Group rows according to datetime (per hour) and get the lowest price for each group (per hour):
            # df = df.groupby(pd.Grouper(key="datetime", freq='H'))['price'].nlargest(3)
            # df = df.groupby(pd.Grouper(key="datetime", freq='H')).apply(lambda x: x.sort_values(["price"], ascending = True))
            # df = df.groupby(['aws-zone', pd.Grouper(key="datetime", freq='H')]).apply(lambda x: x.sort_values(["price"], ascending = True))
            # df = df.groupby(pd.Grouper(key="datetime", freq='H')).apply(lambda x: x.nsmallest(1, columns = "price")) # latest

            # SECTION: get unique aws-zones present in the data:
            # df = df['aws-zone'].drop_duplicates().sort_values()

            # Print all rows, don't want some to be collapsed:
            pd.set_option('display.max_rows', None)
            print(df)
            print(df.shape)

            # SECTION: finally, analyze optimal vs baseline (static) spot price: 
            # Get last row of df:
            df_optimal = df.copy()

            df = df[df['datetime'] == start_date]
            baseline_static_instance_type = df.iloc[-1]['instance-type'] # the baseline will use the cheapest instance type at the beginning of the month. 
            baseline_static_zone = df.iloc[-1]['aws-zone']
            baseline_static_region = get_aws_format_region(df.iloc[-1]['aws-zone']) # the baseline will use the cheapest instance type at the beginning of the month.
            # get index of last row:
            baseline_static_row_id = df[df['datetime'] == start_date].index[-1]
            df_baseline_static_instance_type_only = df_original[df_original['instance-type'] == baseline_static_instance_type]
            # print(df_baseline_static_instance_type_only)
            df_baseline_static_instance_type_only = df_baseline_static_instance_type_only[df_baseline_static_instance_type_only['aws-zone'] == baseline_static_zone]

            # Remove rows that come before the baseline static row, from the optimal schedule, and baseline schedule:
            df_baseline_static_instance_type_only = df_baseline_static_instance_type_only[df_baseline_static_instance_type_only.index >= baseline_static_row_id]
            print(df_baseline_static_instance_type_only)

            df_optimal = df_optimal[df_optimal.index >= baseline_static_row_id]
            print(df_optimal)
            # while True:
            #     x=1

            # Get the total cost of the optimal schedule:
            my_session = boto3.session.Session(profile_name='spotproxy-pat-umich-role')
            ec2 = my_session.client('ec2', 'us-east-1')
            optimal_single_cost, cost_arbitrage_intervals = calculate_cost(ec2, df_optimal, end_date, start_date)
            optimal_multi_cost , _ = calculate_cost(ec2, df_optimal, end_date, start_date, multi_nic=True)
            baseline_static_spotvm_cost, _ = calculate_cost(ec2, df_baseline_static_instance_type_only, end_date, start_date)

            print("Optimal monthly cost for a single spot instance for month {} and year {}: ".format(month, year), optimal_single_cost)
            print("Optimal monthly cost for a single spot instance with multi-NIC for month {} and year {}: ".format(month, year), optimal_multi_cost)
            print("Baseline static monthly cost for a single spot instance for month {} and year {}: ".format(month, year), baseline_static_spotvm_cost)
            print("Baseline static instance type for month {} and year {}:".format(month, year), baseline_static_instance_type)

            # Add to dict:
            price_history_details[month + ", " + year]['optimal_single_cost'] = optimal_single_cost
            price_history_details[month + ", " + year]['optimal_multi_cost'] = optimal_multi_cost
            price_history_details[month + ", " + year]['baseline_static_spotvm_cost'] = baseline_static_spotvm_cost
            price_history_details[month + ", " + year]['baseline_static_instance_type'] = baseline_static_instance_type
            price_history_details[month + ", " + year]['cost_arbitrage_intervals'] = cost_arbitrage_intervals

            # Use AWS Pricing API through Boto3
            # API only has us-east-1 and ap-south-1 as valid endpoints.
            # It doesn't have any impact on your selected region for your instance.
            client = boto3.client('pricing', region_name='us-east-1')
            # Get current price for a given instance, region and os
            # price = get_price(get_region_name('us-east-1'), 't3.micro', 'Linux')
            baseline_static_normalvm_cost = get_price(get_region_name(baseline_static_region), baseline_static_instance_type, 'Linux')
            # print(price)
            price_history_details[month + ", " + year]['baseline_static_normalvm_cost'] = (float(baseline_static_normalvm_cost)+0.005) * 24 * calendar.monthrange(int(year), int(month))[1] # 24 hours in a day, and the number of days in the month            

    print(pretty_json(price_history_details))
    pretty_json(price_history_details, 'price-history-details-min{}-max{}.json'.format(str(min_cost), str(max_cost)))

    # TODO: add the percentage cost savings. This can be done post-processing.








