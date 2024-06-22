import api
import time
import math

class Rejuvenator:
    """Abstract class for rejuvenators."""

    def __init__(self, initial_region, launch_templates, input_args, filter, tag_prefix, print_filename) -> None:
        """Initializes the Rejuvenator object."""

        self.input_args = input_args
        self.initial_region = initial_region
        self.launch_templates = launch_templates
        self.filter = filter
        self.tag_prefix = tag_prefix
        self.print_filename = print_filename

        # Extract required input args:
        self.REJUVENATION_PERIOD = int(input_args['REJUVENATION_PERIOD']) # in seconds
        self.regions = input_args['regions']
        self.PROXY_COUNT = int(input_args['PROXY_COUNT']) # aka fleet size 
        self.PROXY_IMPL = input_args['PROXY_IMPL'] # wireguard | snowflake
        self.batch_size = input_args['batch_size'] # number of instances to create per thread. Currently, we assume this is completely divisible by PROXY_COUNT.
        # self.MIN_COST = float(input_args['MIN_COST'])
        # self.MAX_COST = float(input_args['MAX_COST'])
        # self.MIN_VCPU = int(input_args['MIN_VCPU']) # not used for now
        # self.MAX_VCPU = int(input_args['MAX_VCPU']) # not used for now
        # self.INITIAL_EXPERIMENT_INDEX = int(input_args['INITIAL_EXPERIMENT_INDEX'])
        self.multi_nic = input_args['multi_NIC'] # boolean
        self.mode = input_args['mode'] # liveip | instance 
        # self.data_dir = input_args['dir'] # used for placing the logs.
        self.wait_time_after_create = input_args['wait_time_after_create'] # e.g., 30
        self.wait_time_after_nic = input_args['wait_time_after_nic'] # e.g., 30

    def print_stdout_and_filename(self, string, filename):
        print(string)
        with open(filename, 'a') as file:
            file.write(string + "\n")

    def create_fleet(self, initial_ec2):
        """
            Creates the required fleet: 
            Parameters:
                filter: refer to get_cheapest_instance_types_df for definition 
                tag_prefix: will be used to tag all resources associated with this instance 
                multi_NIC == True, used for liveIP and optimal
                wait_time_after_create: in seconds

            Returns:
                List of created instances (count guaranteed to be proxy_count)
                    [
                        {
                            'InstanceID': instance_id,
                            'InstanceType': instance_type,
                            'InstanceCost': float,
                            'NICs': [(NIC ID, EIP ID, ASSOCIATION ID), ...]
                        },
                        ...
                    ]

                Note, for instance rejuvenation, the list is slightly different:
                    [
                            {
                                'InstanceID': instance_id,
                                'InstanceType': instance_type,
                                'InstanceCost': float,
                                'ec2_session': <ec2-session-object>,
                                'ce_session': <ce-session-object>,
                                'NICs': [(NIC ID, EIP ID, ASSOCIATION ID), ...]
                            },
                            ...
                    ]
        """
        start_time = time.time()
        prices = api.get_cheapest_instance_types_df(initial_ec2, self.filter, multi_NIC=self.multi_nic)
        instance_list = self.loop_create_fleet(initial_ec2, prices)
        self.print_stdout_and_filename("Create fleet success with details: " + api.pretty_json(instance_list), self.print_filename)
        end_time = time.time()
        self.print_stdout_and_filename("Time taken to create fleet: " + str(end_time - start_time), self.print_filename)
        return instance_list

    def loop_create_fleet(self, initial_ec2, prices):
        proxy_count_remaining = self.PROXY_COUNT
        instance_list = []
        # ec2_list = []
        # ce_list = []
        self.print_stdout_and_filename("Original number of rows in prices dataframe: " + str(len(prices.index)), self.print_filename)
        # df.to_string(header=False, index=False)
        self.print_stdout_and_filename(prices.to_string(), self.print_filename) # https://stackoverflow.com/a/58070237/13336187
        count = 1
        prices = prices.reset_index(drop=True) # reset index. https://stackoverflow.com/a/20491748/13336187

        optimal_cheapest_instance_details = None
        first_iteration = True

        while proxy_count_remaining > 0:
            index, cheapest_instance = api.get_instance_row_with_supported_architecture(initial_ec2, prices)

            if first_iteration:
                max_nics = api.get_max_nics(initial_ec2, cheapest_instance['InstanceType'])
                instances_to_create = math.ceil(self.PROXY_COUNT/max_nics) # this is only used for liveip (i.e., multi-NIC) scenario
                optimal_cheapest_instance_details = {"OptimalInstanceCost": cheapest_instance['SpotPrice'], "OptimalInstanceType": cheapest_instance['InstanceType'], "OptimalInstanceZone": cheapest_instance['AvailabilityZone'], "OptimalInstanceMaxNICs": max_nics, "OptimalInstanceCount": instances_to_create}
                first_iteration = False

            prices = prices[index+1:] # if we repeat this loop, it means that we were not able to create enough instances of this type (i.e., index), so we should search from there onwards.
            self.print_stdout_and_filename("Iteration {}: Number of rows in prices dataframe: ".format(count) + str(len(prices.index)), self.print_filename)
            # df.to_string(header=False, index=False)
            self.print_stdout_and_filename(prices.to_string(), self.print_filename) # https://stackoverflow.com/a/58070237/13336187
            cheapest_instance_region = cheapest_instance['AvailabilityZone'][:-1]
            ec2, ce = api.choose_session(region=cheapest_instance_region)
            instance_list_now, proxy_count_remaining = self._create_fleet(ec2, cheapest_instance, proxy_count_remaining)

            for ins in instance_list_now:
                ins['ec2_session_region'] = cheapest_instance_region
                ins['ce_session_region'] = cheapest_instance_region
                ins['optimal_cheapest_instance'] = optimal_cheapest_instance_details
            # ec2_list.extend([ec2 for i in range(len(instance_list_now))]) # each instance will have its own ec2 session (in case this is different across instances...)
            # ce_list.extend([ce for i in range(len(instance_list_now))]) # each instance will have its own ce session (in case this is different across instances...)
            instance_list.extend(instance_list_now)
            count += 1

        return instance_list

    def rejuvenate(self):
        """Rejuvenates the instances."""
        raise NotImplementedError("Subclasses must implement rejuvenate method")

    def _create_fleet(self, ec2, cheapest_instance, proxy_count_remaining):
        """Rejuvenator specific fleet creation."""
        raise NotImplementedError("Subclasses must implement _create_fleet method")

    def handle_reclamation(self):
        """Handles reclamation of resources."""
        pass

    def handle_autoscaling(self):
        """Handles autoscaling of resources."""
        pass


class InstanceRejuvenator(Rejuvenator):
    """Rejuvenator for instances."""

    def __init__(self, initial_region, launch_templates, input_args, filter, tag_prefix, print_filename) -> None:
        """Initializes the InstanceRejuvenator object."""
        super().__init__(initial_region, launch_templates, input_args, filter, tag_prefix, print_filename)

    def rejuvenate(self):
        """Rejuvenates the instances."""
        """
            Runs in a loop. 

            Parameters:
                rej_period: in seconds
                wait_time_after_create: in seconds
                wait_time_after_nic: in seconds
                    - Time to wait before pinging the instance. This is to allow the instance to be fully instantiated before pinging it.

            Returns: None
        """

        instance_lists = []

        self.print_stdout_and_filename("Begin Rejuvenation count: " + str(1), self.print_filename)
        ec2, ce = api.choose_session(region=self.initial_region)

        # Create fleet (with tag values as indicated above):
        instance_list_prev = self.create_fleet(ec2)
        instance_lists.extend(instance_list_prev)
        # Make sure instance can be sshed/pinged (fail rejuvenation if not):
        time.sleep(self.wait_time_after_nic)
        ec2_region = instance_list_prev[0]['ec2_session_region']
        ec2, ce = api.choose_session(region=ec2_region)
        for index, instance_details in enumerate(instance_list_prev):
            if instance_details['ec2_session_region'] != ec2_region:
                ec2_region = instance_details['ec2_session_region']
                ec2, ce = api.choose_session(region=ec2_region)
            failed_ips = api.ping_instances(ec2, instance_details['NICs'], multi_NIC=self.multi_nic)
            if len(failed_ips) != 0:
                self.print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), self.print_filename)
                assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)
        
        # Sleep for rej_period:
        self.print_stdout_and_filename("Sleeping for {} seconds until next rejuvenation period..".format(self.REJUVENATION_PERIOD), self.print_filename)
        time.sleep(self.REJUVENATION_PERIOD)
        
        # Continue with rejuvenation:
        rejuvenation_index = 2
        while True:
            # refresh_credentials() # assume usage of permanent credentials for now
            # print("Begin Rejuvenation count: ", rejuvenation_index)
            self.print_stdout_and_filename("Begin Rejuvenation count: " + str(rejuvenation_index), self.print_filename)

            # Create fleet (with tag values as indicated above):
            ec2, ce = api.choose_session(region=self.initial_region)
            instance_list = self.create_fleet(ec2)

            # Make sure instance can be sshed/pinged (fail rejuvenation if not):
            time.sleep(self.wait_time_after_nic)
            ec2_region = instance_list[0]['ec2_session_region']
            ec2, ce = api.choose_session(region=ec2_region)
            for index, instance_details in enumerate(instance_list):
                if instance_details['ec2_session_region'] != ec2_region:
                    ec2_region = instance_details['ec2_session_region']
                    ec2, ce = api.choose_session(region=ec2_region)
                failed_ips = api.ping_instances(ec2, instance_details['NICs'], multi_NIC=False)
                if len(failed_ips) != 0:
                    self.print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), self.print_filename)
                    assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)

            # Terminate fleet:
            # Chunk list into groups of 100: Maybe work on this next time..
            # chunk_terminate_instances(instance_list_prev, 100)
            # def chunk_terminate_instances(instance_list, chunk_size):
            #     for index, chunk in enumerate(list(chunks(instance_list, chunk_size))):
            #         instance_ids = [instance_details['InstanceID'] for instance_details in chunk]
            #         for ec2 in ec2_list:
            #             api.terminate_instances(ec2, instance_ids)
            self.print_stdout_and_filename("Terminating instances from previous rejuvenation period..", self.print_filename)
            for index, instance_details in enumerate(instance_list_prev):
                if instance_details['ec2_session_region'] != ec2_region:
                    ec2_region = instance_details['ec2_session_region']
                    ec2, ce = api.choose_session(region=ec2_region)
                instance = instance_details['InstanceID']
                api.terminate_instances(ec2, [instance])
            self.print_stdout_and_filename("Instances terminated from previous rejuvenation period..", self.print_filename)

            # To be terminated in next rejuvenation:
            instance_list_prev = instance_list
            instance_lists.extend(instance_list_prev)
            
            # Sleep for rej_period:
            self.print_stdout_and_filename("Sleeping for {} seconds until next rejuvenation period..".format(self.REJUVENATION_PERIOD), self.print_filename)
            time.sleep(self.REJUVENATION_PERIOD)

            # Print new details:
            # print("Concluded Rejuvenation count: ", rejuvenation_index)
            self.print_stdout_and_filename("Concluded Rejuvenation count: " + str(rejuvenation_index), self.print_filename)
            # print("New instance details: ", pretty_json(instance_list))
            self.print_stdout_and_filename("New instance details: " + api.pretty_json(instance_list), self.print_filename)
            rejuvenation_index += 1
        
        # Terminate remaining instances:
        # refresh_credentials()
        ec2_region = instance_list_prev[0]['ec2_session_region']
        ec2, ce = api.choose_session(region=ec2_region)
        for index, instance_details in enumerate(instance_list_prev):
            instance = instance_details['InstanceID']
            if instance_details['ec2_session_region'] != ec2_region:
                ec2_region = instance_details['ec2_session_region']
                ec2, ce = api.choose_session(region=ec2_region)
            api.terminate_instances(ec2, [instance])
        
        # Get total cost:
        # total_cost, optimal_total_cost, total_monthly_cost, optimal_monthly_cost = calculate_cost(instance_lists, rej_period, exp_duration, multi_NIC=False, rej_count=rejuvenation_index-1)
        # print_stdout_and_filename("Total cost of this instance rejuvenation experiment: {}. Optimal total cost (single-NIC) is: {}".format(total_cost, optimal_total_cost), print_filename)
        # print_stdout_and_filename("Total monthly cost of this instance rejuvenation experiment: {}. Optimal total monthly cost (single-NIC) is: {}".format(total_monthly_cost, optimal_monthly_cost), print_filename)
        # # print("Total cost of this instance rejuvenation experiment: {}".format())

        return 

    def _create_fleet(self, ec2, cheapest_instance, proxy_count_remaining):
    # def create_fleet_instance_rejuvenation(ec2, cheapest_instance, proxy_count, proxy_impl, tag_prefix, wait_time_after_create=15, print_filename="data/output-general.txt"):
        """
            Creates fleet combinations. 

            Parameters:
                - cheapest_instance: row of the cheapest instance type (from get_cheapest_instance_types_df)
                - proxy_impl: "snowflake" | "wireguard" | "baseline"
                - tag_prefix: "instance-expX" 
                - wait_time_after_create: in seconds
        """
        # Get the cheapest instance now:
        instance_type_cost = cheapest_instance['SpotPrice']
        instance_type = cheapest_instance['InstanceType']
        zone = cheapest_instance['AvailabilityZone']
        region = zone[:-1] # e.g., us-east-1a -> us-east-1

        # Get suitable launch template based on the region associated with the zone:
        launch_template = self.launch_templates[0] # only 1 launch template for now..

        # Create the initial fleet with multiple NICs (with tag values as indicated above)
        response = api.create_fleet(ec2, instance_type, zone, launch_template, proxy_count_remaining)
        time.sleep(self.wait_time_after_create) # wait awhile for fleet to be created
        # make sure that the required instances have been acquired: 
        print(response['FleetId'])
        all_instance_details = api.get_specific_instances_with_fleet_id_tag(ec2, response['FleetId'], "raw") 
        if len(all_instance_details) != proxy_count_remaining:
            warnings.warn("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(proxy_count_remaining) + " were required.")
            print_stdout_and_filename("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(proxy_count_remaining) + " were required.", print_filename)
        proxy_count_remaining = proxy_count_remaining - len(all_instance_details)

        # print("Created {} instances of type {}, and hourly cost {}. Remaining instances to create: {}".format(len(all_instance_details), instance_type, instance_type_cost, proxy_count_remaining))
        self.print_stdout_and_filename("Created {} instances of type {}, and hourly cost {}. Remaining instances to create: {}".format(len(all_instance_details), instance_type, instance_type_cost, proxy_count_remaining), self.print_filename)

        instance_list = []

        for index, original_instance_details in enumerate(all_instance_details):
            instance = original_instance_details['InstanceId']
            # Tag created instance:
            instance_tag = self.tag_prefix + "-instance{}".format(str(index))
            # api.assign_name_tags(ec2, instance, instance_tag) # TODO: removed for now pending increase limit..
            
            instance_details = {'InstanceID': instance, 'InstanceCost': instance_type_cost, 'InstanceType': instance_type, 'NICs': []}
            # Get original NIC attached to the instance:
            original_nic = original_instance_details['NetworkInterfaces'][0]['NetworkInterfaceId']
            original_pub_ip = original_instance_details['PublicIpAddress']
            assert len(original_instance_details['NetworkInterfaces']) == 1, "Expected only 1 NIC, but got " + str(len(original_instance_details['NetworkInterfaces']))
            # _ , original_nic = api.get_specific_instances_attached_components(ec2, instance)

            # Tag the original NIC:
            instance_details['NICs'] = [(original_nic, original_pub_ip)]
            nic_tag = instance_tag + "-nic{}".format(str(1))
            # api.assign_name_tags(ec2, original_nic, nic_tag) # TODO: removed for now pending increase limit..

            instance_list.append(instance_details) 

        return instance_list, proxy_count_remaining

    # def handle_reclamation(self):
    #     """Handles reclamation of resources."""
    #     super().handle_reclamation()

    # def handle_autoscaling(self):
    #     """Handles autoscaling of resources."""
    #     super().handle_autoscaling()


class LiveIPRejuvenator(Rejuvenator):
    """Rejuvenator for live IPs."""

    def __init__(self, initial_region, launch_templates, input_args, filter, tag_prefix, print_filename) -> None:
        """Initializes the LiveIPRejuvenator object."""
        super().__init__(initial_region, launch_templates, input_args, filter, tag_prefix, print_filename)

    def rejuvenate(self):
        """Rejuvenates the live IPs."""
    # def live_ip_rejuvenation_safe(initial_ec2_region, is_UM, rej_period, proxy_count, exp_duration, proxy_impl, filter=None, tag_prefix="liveip-expX", wait_time_after_create=15, wait_time_after_nic=30, print_filename="data/output-general.txt"):
        try:
            return self.live_ip_rejuvenation()
        except Exception as e:
            self.print_stdout_and_filename("Error occurred: " + str(e), self.print_filename)
            return -1
    
    def live_ip_rejuvenation(self):
        """
            Runs in a loop. 

            Parameters:
                rej_period: in seconds
                exp_duration: in minutes 
                proxy_impl = "wireguard"
                tag_prefix = "liveip-exp" + str(INITIAL_EXPERIMENT_INDEX)
                filter = {
                    "min_cost": 0.002,
                    "max_cost": 0.3,
                    "regions": ["us-east-1"]
                }
                wait_time_after_create: in seconds
                wait_time_after_nic: in seconds
                    - Time to wait before pinging the instance. This is to allow the instance to be fully instantiated before pinging it.

            Returns: cost of this experiment
        """

        self.print_stdout_and_filename("Begin Rejuvenation count: " + str(1), self.print_filename)

        # Create initial fleet (with tag values as indicated above):
        ec2, ce = api.choose_session(region=self.initial_region)
        instance_list = self.create_fleet(ec2)

        # Make sure instance can be sshed/pinged (fail rejuvenation if not):
        time.sleep(self.wait_time_after_nic)
        start_time = time.time()
        ec2_region = instance_list[0]['ec2_session_region']
        ec2, ce = api.choose_session(region=ec2_region)
        for instance_details in instance_list:
            if instance_details['ec2_session_region'] != ec2_region:
                ec2_region = instance_details['ec2_session_region']
                ec2, ce = api.choose_session(region=ec2_region)
            failed_ips = api.ping_instances(ec2, instance_details['NICs'], multi_NIC=True)
            if len(failed_ips) != 0:
                self.print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), self.print_filename)
                raise Exception("Failed to ssh/ping into instances: " + str(failed_ips))
            # assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)
        
        end_time = time.time()
        self.print_stdout_and_filename("Time taken to ping newly created fleet: " + str(end_time - start_time), self.print_filename)

        # Sleep for rej_period:
        time.sleep(self.REJUVENATION_PERIOD)

        # Continue with rejuvenation:
        rejuvenation_index = 2
        while True:
            # refresh_credentials()
            start_time = time.time()
            # ec2, ce = api.choose_session(is_UM_AWS=is_UM, region=cheapest_instance_region)
            self.print_stdout_and_filename("Begin Rejuvenation count: " + str(rejuvenation_index), self.print_filename)
            ec2, ce = api.choose_session(region=ec2_region)
            for index, instance_details in enumerate(instance_list): 
                if instance_details['ec2_session_region'] != ec2_region:
                    ec2_region = instance_details['ec2_session_region']
                    ec2, ce = api.choose_session(region=ec2_region)
                instance_tag = self.tag_prefix + "-instance{}".format(str(index))
                instance = instance_details['InstanceID']
                new_nic_details = []
                for index2, nic_details in enumerate(instance_details['NICs']):
                    start_time2 = time.time()
                    # Deassociate and deallocate NICs from instances (including original one) (with tag values as indicated above):
                    api.disassociate_address(ec2, nic_details[2])
                    api.release_address(ec2, nic_details[1])

                    nic = nic_details[0]

                    # Allocate and associate elastic IPs to all of the NICs (including original one) (with tag values as indicated above):
                    # eip = api.create_eip(ec2, nic, tag)
                    eip = api.get_eip_id_from_allocation_response(api.allocate_address(ec2))
                    # api.associate_address(ec2, instance, eip, nic)
                    assoc_id = api.get_association_id_from_association_response(api.associate_address(ec2, instance, eip, nic))
                    new_nic_details.append((nic, eip, assoc_id))

                    end_time2 = time.time()
                    self.print_stdout_and_filename("Time taken to rejuvenate this NIC (EIP): " + str(end_time2 - start_time2), self.print_filename)

                    # Tag NICs and EIPs:
                    nic_tag = instance_tag + "-nic{}".format(str(index2))
                    eip_tag = nic_tag + "-eip{}".format(str(index2))
                    # api.assign_name_tags(ec2, nic, nic_tag) # TODO: bypass Request limit exceeded for now
                    # api.assign_name_tags(ec2, eip, eip_tag) # TODO: bypass Request limit exceeded for now
                instance_details['NICs'] = new_nic_details
        
            # Make sure instance can be sshed/pinged (fail rejuvenation if not):
            time.sleep(self.wait_time_after_nic)
            ec2, ce = api.choose_session(region=ec2_region)
            for instance_details in instance_list:
                if instance_details['ec2_session_region'] != ec2_region:
                    ec2_region = instance_details['ec2_session_region']
                    ec2, ce = api.choose_session(region=ec2_region)
                failed_ips = api.ping_instances(ec2, instance_details['NICs'], multi_NIC=True)
                if len(failed_ips) != 0:
                    with open(print_filename, 'a') as file:
                        self.print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), self.print_filename)
                        assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)

            # Print new details:
            # print("Concluded Rejuvenation count: ", rejuvenation_index)
            self.print_stdout_and_filename("Concluded Rejuvenation count: " + str(rejuvenation_index), self.print_filename)
            end_time = time.time()
            self.print_stdout_and_filename("Time taken to ping newly created fleet: " + str(end_time - start_time), self.print_filename)
            # print("New instance details: ", pretty_json(instance_list))
            self.print_stdout_and_filename("New instance details: " + api.pretty_json(instance_list), self.print_filename)
            rejuvenation_index += 1

            # Sleep for rej_period:
            time.sleep(self.REJUVENATION_PERIOD)

        # refresh_credentials()

        # Get total cost:
        # total_cost, optimal_total_cost, total_monthly_cost, optimal_monthly_cost = calculate_cost(instance_list, rej_period, exp_duration, multi_NIC=True, rej_count=rejuvenation_index-1)
        # # print("Total cost of this live IP rejuvenation experiment: {}".format(total_cost))
        # print_stdout_and_filename("Total cost of this live IP rejuvenation experiment: {}. Optimal total cost (multi-NIC) is: {}".format(total_cost, optimal_total_cost), print_filename)
        # print_stdout_and_filename("Total monthly cost of this live IP rejuvenation experiment: {}. Optimal monthly cost (multi-NIC) is: {}".format(total_monthly_cost, optimal_monthly_cost), print_filename)

        # Remove instances (and NICs) and EIPs: TODO: move this into a finally block after termination..
        start_time = time.time()
        ec2, ce = api.choose_session(region=ec2_region)
        for instance_details in instance_list:
            if instance_details['ec2_session_region'] != ec2_region:
                ec2_region = instance_details['ec2_session_region']
                ec2, ce = api.choose_session(region=ec2_region)
            for nic_details in instance_details['NICs']:
                api.disassociate_address(ec2, nic_details[2])
                api.release_address(ec2, nic_details[1])
            instance = instance_details['InstanceID']
            api.terminate_instances(ec2, [instance])
        end_time = time.time()
        self.print_stdout_and_filename("Time taken to clean up after rejuvenation has completed: " + str(end_time - start_time), self.print_filename)
        
        return 

    def _create_fleet(self, ec2, cheapest_instance, proxy_count_remaining):
    # def create_fleet_live_ip_rejuvenation(ec2, cheapest_instance, proxy_count, proxy_impl, tag_prefix, wait_time_after_create=15, print_filename="data/output-general.txt"):
        """
            Creates fleet combinations. 

            Parameters:
                - cheapest_instance: row of the cheapest instance type (from get_cheapest_instance_types_df)
                - proxy_impl: "snowflake" | "wireguard" | "baseline"
                - tag_prefix: "liveip-expX" 
                - wait_time_after_create: in seconds
        """

        # Get the cheapest instance now:
        instance_type_cost = cheapest_instance['SpotPrice']
        instance_type = cheapest_instance['InstanceType']
        zone = cheapest_instance['AvailabilityZone']
        region = zone[:-1] # e.g., us-east-1a -> us-east-1

        # Get the number of NICs in this instance type:
        max_nics = api.get_max_nics(ec2, instance_type)
        # Get number of instances needed:
        instances_to_create = math.ceil(proxy_count_remaining/max_nics)

        # Get suitable launch template based on the region associated with the zone:
        launch_template = self.launch_templates[0] # only 1 launch template for now..

        # Create the initial fleet with multiple NICs (with tag values as indicated above)
        response = api.create_fleet(ec2, instance_type, zone, launch_template, instances_to_create)
        time.sleep(self.wait_time_after_create) # wait awhile for fleet to be created
        # make sure that the required instances have been acquired: 
        print(response['FleetId'])
        print(api.pretty_json(response))
        all_instance_details = api.get_specific_instances_with_fleet_id_tag(ec2, response['FleetId'], "raw") 
        if len(all_instance_details) != instances_to_create:
            warnings.warn("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(instances_to_create) + " were required.")
            self.print_stdout_and_filename("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(instances_to_create) + " were required.", self.print_filename)

        if proxy_count_remaining % max_nics: # i.e., where there is a remainder:
            proxy_count_remaining = proxy_count_remaining % max_nics + (instances_to_create - len(all_instance_details) - 1) * max_nics
        else: # i.e., where there is no remainder
            proxy_count_remaining = (instances_to_create - len(all_instance_details)) * max_nics

        # print("Created {} instances of type {} with {} NICs each, and hourly cost {}".format(instances_to_create, instance_type, max_nics, instance_type_cost))
        self.print_stdout_and_filename("Created {} instances of type {} with {} NICs each, and hourly cost {}. Remaining proxies to create: {}".format(len(all_instance_details), instance_type, max_nics, instance_type_cost, proxy_count_remaining), self.print_filename)

        instance_list = []

        for index, original_instance_details in enumerate(all_instance_details):
            instance = original_instance_details['InstanceId']
            # Tag created instance:
            instance_tag = self.tag_prefix + "-instance{}".format(str(index))
            # api.assign_name_tags(ec2, instance, instance_tag) # TODO: bypass Request limit exceeded for now
            
            instance_details = {'InstanceID': instance, 'InstanceCost': instance_type_cost, 'InstanceType': instance_type, 'NICs': []}
            # Get original NIC attached to the instance:
            original_nic = original_instance_details['NetworkInterfaces'][0]['NetworkInterfaceId']
            assert len(original_instance_details['NetworkInterfaces']) == 1, "Expected only 1 NIC, but got " + str(len(original_instance_details['NetworkInterfaces']))
            # _ , original_nic = api.get_specific_instances_attached_components(ec2, instance)

            # Create the NICs and associate them with the instances:
            nics = api.create_nics(ec2, instance, max_nics-1, zone)

            nics.append(original_nic)
            # Create the elastic IPs and associate them with the NICs:
            for index2, nic in enumerate(nics):
                # eip = api.create_eip(ec2, nic, tag)
                eip = api.get_eip_id_from_allocation_response(api.allocate_address(ec2))
                # print(api.associate_address(ec2, instance, eip, nic))
                assoc_id = api.get_association_id_from_association_response(api.associate_address(ec2, instance, eip, nic))
                instance_details['NICs'].append((nic, eip, assoc_id))

                # Tag NICs and EIPs:
                nic_tag = instance_tag + "-nic{}".format(str(index2))
                eip_tag = nic_tag + "-eip{}".format(str(index2))
                # api.assign_name_tags(ec2, nic, nic_tag) # TODO: bypass Request limit exceeded for now
                # api.assign_name_tags(ec2, eip, eip_tag) # TODO: bypass Request limit exceeded for now

            instance_list.append(instance_details) 

        return instance_list, proxy_count_remaining

    # def handle_reclamation(self):
    #     """Handles reclamation of resources."""
    #     super().handle_reclamation()
    
    # def handle_autoscaling(self):
    #     """Handles autoscaling of resources."""
    #     super().handle_autoscaling()