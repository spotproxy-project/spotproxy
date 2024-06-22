def get_matched_clients(client_prefrences, proxy_prefrences, capacities):
    """
    The deferred acceptence algorithm from the Enem19 paper
    """
    waiting_clients = [student for student in client_prefrences]
    assignment_results = {choice: [] for choice in capacities}

    def get_waiting_list_without_student(student):
        return [x for x in waiting_clients if x != student]

    def get_sorted_results_with_student(student, choice):
        assignment_results[choice].append(student)
        return [x for x in proxy_prefrences[choice] if x in assignment_results[choice]]

    while waiting_clients:
        for student in waiting_clients.copy():
            if not client_prefrences[student]:
                waiting_clients = get_waiting_list_without_student(student)
                continue
            choice = client_prefrences[student].pop(0)
            if len(assignment_results[choice]) < capacities[choice]:
                assignment_results[choice] = get_sorted_results_with_student(
                    student, choice
                )
                waiting_clients = get_waiting_list_without_student(student)
            else:
                if proxy_prefrences[choice].index(student) < proxy_prefrences[
                    choice
                ].index(assignment_results[choice][-1]):
                    assignment_results[choice] = get_sorted_results_with_student(
                        student, choice
                    )
                    waiting_clients = get_waiting_list_without_student(student)
                    waiting_clients.append(assignment_results[choice].pop())

    return assignment_results


if __name__ == "__main__":
    # run test
    client_preferences = {
        "client1": ["proxy1", "proxy2", "proxy3"],
        "client2": ["proxy1", "proxy2", "proxy3"],
        "client3": ["proxy2", "proxy3", "proxy1"],
    }

    proxy_preferences = {
        "proxy1": ["client2", "client3", "client1"],
        "proxy2": ["client1", "client3", "client2"],
        "proxy3": ["client2", "client1", "client3"],
    }

    proxy_capacities = {"proxy1": 1, "proxy2": 2, "proxy3": 1}

    print(get_matched_clients(client_preferences, proxy_preferences, proxy_capacities))
