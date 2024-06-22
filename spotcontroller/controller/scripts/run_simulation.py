from random import random
from django.db.models import F
from tqdm import tqdm
from assignments.models import (
    Client,
    Proxy,
    Assignment,
    ChartNonBlockedProxyRatio,
    ChartConnectedUsersRatio,
    ChartNonBlockedProxyCount,
)
from .Censor import *
from .config_basic import *
from .simulation_utils import request_new_proxy, request_new_proxy_new_client
from time import time, sleep
import os


def run_simulation(
    censor_type,
    censoring_agent_ratio,
    censoring_agent_ratio_birth_period,
    rejuvination_interval,
):
    # TODO: change this
    # censor = AggresiveCensor()
    if censor_type == "OPTIMAL":
        print("optimal censor")
        censor = OptimalCensor()
    else:
        print("aggressive censor")
        censor = AggresiveCensor()
    print(f"rej: {rejuvination_interval}")
    print(f"censor rate: {censoring_agent_ratio}")
    duration = BIRTH_PERIOD + SIMULATION_DURATION
    last_created_proxy_ip = "0.0.0.0"
    last_created_client_id = -1
    Proxy.objects.create(ip=last_created_proxy_ip, is_test=True)

    for step in tqdm(range(duration)):
        is_birth_period = False
        if step < BIRTH_PERIOD:
            is_birth_period = True

        # time1 = time()
        # Censor chooses what proxies of the ones they have to block
        blocked_clients = []
        # TODO: do the actual censors
        list_of_proxies_to_be_blocked = censor.run(step)
        for proxy in list_of_proxies_to_be_blocked:
            proxy.is_blocked = True
            proxy.blocked_at = step
            proxy.save()
            blocked_ip_list = (
                Assignment.objects.filter(proxy=proxy)
                .values_list("client", flat=True)
                .distinct()
            )
            affected_clients = Client.objects.filter(ip__in=blocked_ip_list)
            affected_clients.update(
                known_blocked_proxies=F("known_blocked_proxies") + 1
            )
            blocked_clients.extend(list(affected_clients))

        # time2 = time()
        # TODO: do the data recordings
        # Number of disconnected users are determined and recorded
        # ChartNonBlockedProxyRatio, ChartConnectedUsersRatio, ChartNonBlockedProxyCount
        # IF the rejuvination interval > 1 then count blocked proxies on intervals where there are no rejuvs
        if rejuvination_interval > 1 and step % rejuvination_interval != 0:
            all_active_proxies_count = Proxy.objects.filter(is_active=True).count()
            blocked_proxies_count = Proxy.objects.filter(
                is_active=True, is_blocked=True
            ).count()
            nonblocked_ratio = (
                all_active_proxies_count - blocked_proxies_count
            ) / all_active_proxies_count
            ChartNonBlockedProxyRatio.objects.create(
                value=nonblocked_ratio, creation_time=step
            )
            nonblocked_count = all_active_proxies_count - blocked_proxies_count
            ChartNonBlockedProxyCount.objects.create(
                value=nonblocked_count, creation_time=step
            )
            flagged_count = Client.objects.filter(
                flagged=True, is_censor_agent=False
            ).count()
            total_count = Client.objects.all().count()
            # TODO: maybe a distinct might be good here?
            affected_clients_this_step = len(blocked_clients)
            try:
                connected_user_ratio = (
                    total_count - flagged_count - affected_clients_this_step
                ) / total_count
            except:
                print("this happens once!")
                connected_user_ratio = 0
            ChartConnectedUsersRatio.objects.create(
                value=connected_user_ratio, creation_time=step
            )
        else:
            ChartNonBlockedProxyRatio.objects.create(value=1.0, creation_time=step)
            ChartNonBlockedProxyCount.objects.create(
                value=Proxy.objects.filter(is_active=True).count(), creation_time=step
            )
            flagged_count = Client.objects.filter(
                flagged=True, is_censor_agent=False
            ).count()
            total_count = Client.objects.all().count()
            try:
                connected_user_ratio = (total_count - flagged_count) / total_count
            except:
                print("this happens once!")
                connected_user_ratio = 0
            ChartConnectedUsersRatio.objects.create(
                value=connected_user_ratio, creation_time=step
            )

        # time3 = time()
        #   DONE: Rejuvinate
        if step % rejuvination_interval == 0:
            rejuvinate(step)

        # time4 = time()
        # Done: at some point I should decide when the agents request for new proxies
        #   DONE: Affected clients (agent or not) request for new proxies and see if they're blocked or not.
        #   DONE: The get proxy algo gets run for every single client that was previously connected to those blocked proxies
        request_new_proxy(proposing_clients=blocked_clients, right_now=step)

        # time5 = time()
        # DONE: New proxies (if any) get created
        if step % NEW_PROXY_INTERVAL == 0:
            for _ in range(NEW_PROXY_COUNT):
                last_created_proxy_ip = create_new_proxy(last_created_proxy_ip)

        # DONE: New clients get added (censor agent with chance of censoring agent)
        if step % NEW_USER_RATE_INTERVAL == 0:
            for _ in range(NEW_USER_COUNT):
                last_created_client_id = create_new_client(
                    censor,
                    last_created_client_id,
                    is_birth_period,
                    step,
                    censoring_agent_ratio,
                    censoring_agent_ratio_birth_period,
                )

        # time6 = time()

        # times = [time2-time1, time3-time2, time4-time3, time5-time4, time6-time5]
        # print(f"taking most time: {times.index(max(times))} ||||||| {times}")


def rejuvinate(step):
    active_proxies = Proxy.objects.filter(is_active=True)
    for proxy in active_proxies:
        old_proxy_ip = proxy.ip
        new_proxy_ip = get_migration_proxies_ip(old_proxy_ip)
        # new_proxy = Proxy.objects.create(ip=new_proxy_ip, is_test=True)
        proxy.ip = new_proxy_ip
        if proxy.is_blocked:
            proxy.is_blocked = False
            proxy.capacity = MAX_PROXY_CAPACITY
            Assignment.objects.filter(proxy=proxy).delete()
        # proxy.deactivated_at = step
        proxy.save()


def get_migration_proxies_ip(old_ip):
    nums = list(map(int, old_ip.split(".")))
    if nums[3] == 255:
        nums[3] = 0
        nums[2] += 1
    else:
        nums[3] += 1

    return f"{nums[0]}.{nums[1]}.{nums[2]}.{nums[3]}"


def create_new_proxy(last_created_proxy_ip):
    nums = list(map(int, last_created_proxy_ip.split(".")))
    if nums[1] == 255:
        nums[1] = 0
        nums[0] += 1
    else:
        nums[1] += 1

    last_created_proxy_ip = f"{nums[0]}.{nums[1]}.{nums[2]}.{nums[3]}"
    Proxy.objects.create(ip=last_created_proxy_ip, is_test=True)
    return last_created_proxy_ip


def create_new_client(
    censor,
    last_created_client_id,
    is_birth_period,
    step,
    censoring_agent_ratio,
    censoring_agent_ratio_birth_period,
):
    client_ip_template = "255.{}.{}.{}"
    client_id = last_created_client_id + 1
    num1 = client_id // (256 * 256)
    num2 = (client_id % (256 * 256)) // 256
    num3 = client_id % 256
    ip = client_ip_template.format(num1, num2, num3)

    censor_chance = censoring_agent_ratio
    if is_birth_period:
        censor_chance = censoring_agent_ratio_birth_period

    if random() < censor_chance:
        cl = Client.objects.create(ip=ip, is_censor_agent=True, creation_time=step)
        censor.agents.append(cl)
    else:
        cl = Client.objects.create(ip=ip, creation_time=step)

    request_new_proxy_new_client(cl, step)

    return client_id


def run(*args):
    ############ CENSOR ############
    CENSOR_TYPE = ["OPTIMAL", "AGGRESIVE"]  # OPTIMAL or AGGRESIVE
    REJUVINATION_INTERVAL = [1, 2]  # rejuvinations are made every this many time units
    CENSORING_AGENTS_TO_ALL_CLIENTS = [0.05, 0.1, 0.5]  # can be 0.05, 0.1, and 0.5
    CENSORING_AGENTS_TO_ALL_CLIENTS_BIRTH_PERIOD_ratio = 0.4

    for censoring_agent_ratio in CENSORING_AGENTS_TO_ALL_CLIENTS:
        for censor_type in CENSOR_TYPE:
            for rejuvination_interval in REJUVINATION_INTERVAL:
                run_simulation(
                    censor_type,
                    censoring_agent_ratio,
                    censoring_agent_ratio
                    * CENSORING_AGENTS_TO_ALL_CLIENTS_BIRTH_PERIOD_ratio,
                    rejuvination_interval,
                )
                nonblockedproxyratio = list(
                    ChartNonBlockedProxyRatio.objects.all().values_list(
                        "value", flat=True
                    )
                )
                nonblockedproxycount = list(
                    ChartNonBlockedProxyCount.objects.all().values_list(
                        "value", flat=True
                    )
                )
                connecteduserratio = list(
                    ChartConnectedUsersRatio.objects.all().values_list(
                        "value", flat=True
                    )
                )
                with open(
                    f"../results/results_{censor_type}_rej{rejuvination_interval}_cens{censoring_agent_ratio}.csv",
                    "w",
                ) as f:
                    f.write(
                        "nonblocked_proxy_ratio,nonblocked_proxy_count,connected_user_ratio\n"
                    )
                    for i in range(len(nonblockedproxycount)):
                        f.write(
                            f"{nonblockedproxyratio[i]},{nonblockedproxycount[i]},{connecteduserratio[i]}\n"
                        )

                print("done")
                os.system("python3 manage.py flush --no-input")
                # os.system("python3 manage.py migrate")
                sleep(3)
                print("ready to go")

    # print(Client.objects.all().count())
    # print('flagged clients:')
    # print(Client.objects.filter(flagged=True).count())
    # print('flagged censor agents:')
    # print(Client.objects.filter(flagged=True, is_censor_agent=True).count())
    # print('all censor agents:')
    # print(Client.objects.filter(is_censor_agent=True).count())
    # print(Proxy.objects.all().count())
    # print(Assignment.objects.all().count())

    # # print("we're live baby!")
    # # pr1 = Proxy.objects.create(ip=f'1.0.0.1', is_test=True, is_active=False)
    # # pr2 = Proxy.objects.create(ip=f'1.0.0.2', is_test=True, is_blocked=True)
    # # pr3 = Proxy.objects.create(ip=f'1.0.0.3', is_test=True)
    # pr4 = Proxy.objects.create(ip=f'1.0.0.4', is_test=True)
    # # pr5 = Proxy.objects.create(ip=f'1.0.0.5', is_test=True)
    # # pr6 = Proxy.objects.create(ip=f'1.0.0.6', is_test=True)
    # # pr7 = Proxy.objects.create(ip=f'1.0.0.7', is_test=True)

    # cl1 = Client.objects.create(ip='2.2.2.2')
    # cl2 = Client.objects.create(ip='3.3.3.3', is_censor_agent=True)
    # # request_new_proxy_new_client(cl1)
    # # request_new_proxy_new_client(cl2)

    # # Assignment.objects.create(proxy=pr1, client=cl, assignment_time=4)
    # # Assignment.objects.create(proxy=pr2, client=cl, assignment_time=2)
    # # Assignment.objects.create(proxy=pr3, client=cl, assignment_time=5)
    # Assignment.objects.create(proxy=pr4, client=cl1, assignment_time=1)

    # print(Client.objects.all())
    # print(Proxy.objects.all())
    # print(Assignment.objects.all())

    # Assignment.objects.filter(proxy=pr4).delete()

    # print(Client.objects.all())
    # print(Proxy.objects.all())
    # print(Assignment.objects.all())

    # # print(request_new_proxy([cl1,cl2], 10))
    # # print(Assignment.objects.filter(client__in=[cl1]).values_list('proxy', flat=True).distinct())
    # # print(request_new_proxy([cl1,cl2], 15))
    # # print(request_new_proxy([cl1,cl2], 20))

    # # print(request_new_proxy('5.5.5.5'))
    # # print(request_new_proxy('5.5.5.5'))
