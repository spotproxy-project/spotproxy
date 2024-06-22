from django.core.exceptions import ObjectDoesNotExist
from rest_framework.response import Response
from rest_framework import status
from assignments.services.startup import id_to_nums
from random import randint
from time import time
from django.db.models import F
from assignments.models import *
from scripts.config_basic import (
    CENSORED_REGION_SIZE,
    MAX_PROXY_CAPACITY,
    CENSOR_UTILIZATION_RATIO,
    CLIENT_UTILITY_THRESHOLD,
)
from scripts.deferred_acceptance import get_matched_clients


def calcualte_distance(point_1, point_2):
    return ((point_1[0] - point_2[0]) ** 2 + (point_1[1] - point_2[1]) ** 2) ** 0.5


def get_normalized_distance(point_1, point_2):
    return calcualte_distance(point_1, point_2) / CENSORED_REGION_SIZE


def get_client_proxy_utilization(client, client_assignments, right_now):
    proxy_checker = {}
    clients_proxy_utilization = 0
    for assignment in client_assignments:
        if proxy_checker.get(assignment.proxy.id, None):
            continue
        if assignment.proxy.is_blocked == True:
            clients_proxy_utilization += (
                assignment.proxy.blocked_at - assignment.assignment_time
            )
        if assignment.proxy.is_active == False:
            clients_proxy_utilization += (
                assignment.proxy.deactivated_at - assignment.assignment_time
            )
        else:
            clients_proxy_utilization += right_now - assignment.assignment_time
        proxy_checker[assignment.proxy.id] = True

    if client.is_censor_agent:
        clients_proxy_utilization = clients_proxy_utilization * CENSOR_UTILIZATION_RATIO
    return clients_proxy_utilization


def request_new_proxy_new_client(client, right_now):
    chosen_proxy = (
        Proxy.objects.filter(is_blocked=False, is_active=True, capacity__gt=0)
        .all()
        .first()
    )

    Assignment.objects.create(
        proxy=chosen_proxy, client=client, assignment_time=right_now
    )
    client.request_count += 1
    client.save()
    if Assignment.objects.filter(proxy=chosen_proxy, client=client).count() == 1:
        chosen_proxy.capacity -= 1
        chosen_proxy.save()
    return chosen_proxy


################### MAIN THING ###################


def request_new_proxy(proposing_clients, right_now: int):
    client_prefrences = {}
    proxy_prefrences = {}
    proxy_capacities = {}
    general_client_utilities = {}
    general_proxy_utilities = {}
    flagged_clients = []

    # time1 = time()

    active_proxies = Proxy.objects.filter(
        is_blocked=False, is_active=True, capacity__gt=0
    ).all()

    # time2 = time()

    alpha1, alpha2, alpha3, alpha4, alpha5 = 2, 1, 1, 2, 10
    some_cap_value = 1000 * 24
    for client in proposing_clients:
        if client.flagged == True:
            continue
        # ################ Enem19 implementation ################
        client_assignments = Assignment.objects.filter(client=client).order_by(
            "created_at"
        )

        blocked_proxy_usage = 0
        for assignment in client_assignments:
            if assignment.proxy.is_blocked == True:
                blocked_proxy_usage += (
                    assignment.proxy.blocked_at - assignment.assignment_time
                )
        number_of_blocked_proxies_that_a_user_knows = client.known_blocked_proxies
        number_of_requests_for_new_proxies = client.request_count
        # clients_proxy_utilization = get_client_proxy_utilization(client, client_assignments, right_now)
        clients_proxy_utilization = right_now - client.creation_time
        if client.is_censor_agent:
            clients_proxy_utilization = (
                clients_proxy_utilization * CENSOR_UTILIZATION_RATIO
            )
        client_utility = (
            alpha1 * min(clients_proxy_utilization, some_cap_value)
            - alpha2 * number_of_requests_for_new_proxies
            - alpha3 * blocked_proxy_usage
            - alpha4 * number_of_blocked_proxies_that_a_user_knows
        )
        general_client_utilities[client.ip] = client_utility

    # time3 = time()

    for proxy in active_proxies:
        utility_values_for_clients = {}
        for client in proposing_clients:
            if client.flagged == True:
                continue
            # ################ Enem19 implementation ################
            distance = get_normalized_distance(
                (proxy.latitude, proxy.longitude), (client.latitude, client.longitude)
            )
            client_utility = general_client_utilities[client.ip] - alpha5 * distance

            if client_utility < CLIENT_UTILITY_THRESHOLD:
                client.flagged = True
                client.save()
                flagged_clients.append(client)
            utility_values_for_clients[client.ip] = client_utility
        proxy_prefrences[proxy.ip] = list(
            reversed(
                sorted(
                    utility_values_for_clients,
                    key=lambda k: utility_values_for_clients[k],
                )
            )
        )
        proxy_capacities[proxy.ip] = proxy.capacity

    # time4 = time()

    beta1, beta2, beta3, beta4 = 1, 1, 1, 1
    for proxy in active_proxies:
        number_of_connected_clients = MAX_PROXY_CAPACITY - proxy.capacity
        number_of_clients_who_know_the_proxy = (
            Assignment.objects.filter(proxy=proxy)
            .values_list("client", flat=True)
            .distinct()
            .count()
        )
        total_utilization_of_proxy_for_users = 0
        proxy_utility = (
            beta1 * number_of_clients_who_know_the_proxy
            + beta2 * number_of_connected_clients
            + beta3 * total_utilization_of_proxy_for_users
        )
        general_proxy_utilities[proxy.ip] = proxy_utility

    for client in proposing_clients:
        if client.flagged == True:
            continue
        utility_values_for_proxies = {}
        beta4 = 1
        for proxy in active_proxies:
            distance = get_normalized_distance(
                (proxy.latitude, proxy.longitude), (client.latitude, client.longitude)
            )
            proxy_utility = general_proxy_utilities[proxy.ip] - beta4 * distance
            utility_values_for_proxies[proxy.ip] = proxy_utility
        client_prefrences[client.ip] = list(
            reversed(
                sorted(
                    utility_values_for_proxies,
                    key=lambda k: utility_values_for_proxies[k],
                )
            )
        )

    # time5 = time()

    matches = get_matched_clients(client_prefrences, proxy_prefrences, proxy_capacities)

    # time6 = time()

    for proxy_id in matches.keys():
        proxy = Proxy.objects.get(ip=proxy_id)
        clients_accepted = matches[proxy_id]
        clients = Client.objects.filter(ip__in=clients_accepted)
        clients.update(request_count=F("request_count") + 1)
        proxy.capacity -= len(clients)
        proxy.save()
        for client in clients:
            Assignment.objects.create(
                proxy=proxy, client=client, assignment_time=right_now
            )
            # if Assignment.objects.filter(proxy=proxy, client=client).count() == 1:

    # time7 = time()

    # times = [time2-time1, time3-time2, time4-time3, time5-time4, time6-time5, time7-time6]
    # print(f"taking most time: {times.index(max(times))} ||||||| {times}")

    return flagged_clients
