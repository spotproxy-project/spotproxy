from assignments.models import *


def run(*args):
    print(
        Proxy.objects.filter(is_blocked=False, is_active=True, capacity__gt=0).count()
    )
    print(Proxy.objects.filter(is_blocked=False).count())
    print(Proxy.objects.filter(is_blocked=False, is_active=True).count())
    print(Proxy.objects.filter(is_active=True, capacity__gt=0).count())

    print(Client.objects.all().count())
    print("flagged clients:")
    print(Client.objects.filter(flagged=True).count())
    print("flagged censor agents:")
    print(Client.objects.filter(flagged=True, is_censor_agent=True).count())
    print("all censor agents:")
    print(Client.objects.filter(is_censor_agent=True).count())
    print(Proxy.objects.all().count())
    print(Assignment.objects.all().count())

    nonblockedproxyratio = list(
        ChartNonBlockedProxyRatio.objects.all().values_list("value", flat=True)
    )
    nonblockedproxycount = list(
        ChartNonBlockedProxyCount.objects.all().values_list("value", flat=True)
    )
    connecteduserratio = list(
        ChartConnectedUsersRatio.objects.all().values_list("value", flat=True)
    )
    with open("results.csv", "w") as f:
        f.write("nonblocked_proxy_ratio,nonblocked_proxy_count,connected_user_ratio\n")
        for i in range(len(nonblockedproxycount)):
            f.write(
                f"{nonblockedproxyratio[i]},{nonblockedproxycount[i]},{connecteduserratio[i]}\n"
            )

    print("done")
