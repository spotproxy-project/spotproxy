import api, json
initial_ec2, initial_ce = api.choose_session(is_UM_AWS=True, region='us-east-1')

addresses_dict = initial_ec2.describe_addresses()
eips_removed = []
nics_removed = []
# Source: https://stackoverflow.com/a/46250750/13336187
for eip_dict in addresses_dict['Addresses']:
    # Remove the EIP: 
    if "InstanceId" not in eip_dict:
        # print(api.pretty_json(eip_dict))
        if "AssociationId" in eip_dict: # if associated to some NIC
            initial_ec2.disassociate_address(AssociationId=eip_dict['AssociationId'])

        initial_ec2.release_address(AllocationId=eip_dict['AllocationId'])
        
        eips_removed.append(eip_dict['PublicIp'])

        # Remove the NIC: edge case not handled: terminate this script early, and the EIP is released before the NIC was removed..
        if "NetworkInterfaceId" in eip_dict:
            initial_ec2.delete_network_interface(NetworkInterfaceId=eip_dict['NetworkInterfaceId'])
            nics_removed.append(eip_dict['NetworkInterfaceId'])

print("NUKED EVERYTING. Total EIPs and NICs terminated: {}, {}".format(str(len(eips_removed)), str(len(nics_removed))))