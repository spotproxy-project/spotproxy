import requests
import threading
from time import time, sleep


def startup():
    from assignments.models import Proxy
    from assignments.services import poller_threads

    if Proxy.objects.all().count() != 0:
        # Note: can be changed if needed
        print("database is already populated")
        return

    INSTANCE_INFO_URL = "http://44.197.203.24:8000/getInitDetails"

    response = requests.get(INSTANCE_INFO_URL)

    response_dict = dict(response.json())
    proxy_ip_list = []

    for key in response_dict.keys():
        proxy_ip_list.append(response_dict[key]["PublicIpAddress"])

    for ip in proxy_ip_list:
        Proxy.objects.create(ip=ip)

    poller_thread = poller_threads.PollerThread()
    poller_thread.start()

    # TODO: Add a system for migrations and stuff, since we don't have the push for the current test


def id_to_nums(id):
    num1 = id // 250
    num2 = id % 250
    return num1, num2


def setup_test_db(test_config):
    from assignments.models import Proxy, Client, Assignment

    MIGRATION_COUNT = 10
    client_count = test_config[0]
    proxy_count = test_config[1]
    clinet_per_proxy = client_count // proxy_count
    # fake_proxy_ip_base = '1.-.-.0' through '1.-.-.10'
    # fake_client_ip_base = '2.-.-.1' through '1.-.-.client_per_proxy'

    for i in range(proxy_count):
        num1, num2 = id_to_nums(i)
        main_proxy = Proxy.objects.create(ip=f"1.{num1}.{num2}.{0}", is_test=True)
        for i in range(MIGRATION_COUNT):
            Proxy.objects.create(ip=f"1.{num1}.{num2}.{i+1}", is_test=True)
        for i in range(clinet_per_proxy):
            client = Client.objects.create(ip=f"2.{num1}.{num2}.{i+1}", is_test=True)
            Assignment.objects.create(proxy=main_proxy, client=client)


def test_startup():
    from assignments.services import test_threads

    TEST_SIZE_C_P = [(100, 10), (500, 50), (1000, 100), (2000, 200), (5000, 50)]
    test_config = TEST_SIZE_C_P[4]
    print(f"going with {test_config[0]}c{test_config[1]}p")
    setup_test_db(test_config)

    poster_thread = test_threads.UpdatePosterThread(test_config[1])
    poster_thread.start()
