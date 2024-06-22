from assignments.models import Assignment, Proxy, Client


class AggresiveCensor:
    def __init__(self) -> None:
        self.agents = []

    def run(self, step):
        # print(self.agents)
        known_proxies = (
            Assignment.objects.filter(client__in=self.agents)
            .values_list("proxy", flat=True)
            .distinct()
        )
        known_proxies_good_for_blocking = Proxy.objects.filter(
            id__in=known_proxies, is_blocked=False, is_active=True
        )
        # print(known_proxies_good_for_blocking)
        return known_proxies_good_for_blocking


class OptimalCensor:
    def __init__(self) -> None:
        self.agents = []

    def run(self, right_now):
        # Based on calcualtions of the chosen alpha and beta params
        known_proxies = (
            Assignment.objects.filter(
                client__in=self.agents, 
                assignment_time__lt=right_now - 2,
                is_expired=False
            )
            .values_list("proxy", flat=True)
            .distinct()
        )
        known_proxies_good_for_blocking = Proxy.objects.filter(
            id__in=known_proxies, is_blocked=False, is_active=True
        )
        return known_proxies_good_for_blocking
