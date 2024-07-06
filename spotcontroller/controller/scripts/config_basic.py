############ CENSOR TYPE ############
# CENSOR_TYPE = "OPTIMAL" # OPTIMAL or AGGRESIVE


############ BASICS ############
# SIMULATION_DURATION = 2 * 365 * 12  # 2 years
SIMULATION_DURATION = 5 * 12  # 5 days. Faster for artifact evaluation purposes. 
BIRTH_PERIOD = 365 * 6  # half a year?
CLIENT_UTILITY_THRESHOLD = -500
WORLD_SIZE = 20000
CENSORED_REGION_SIZE = 1000

MAX_PROXY_CAPACITY = 40
CENSOR_UTILIZATION_RATIO = 0.4

############ RATES ############
# for our reference: TIME_UNIT = 2 hour
NEW_USER_RATE_INTERVAL = 4  # 1 user every 3 units
NEW_USER_COUNT = 1

NEW_PROXY_INTERVAL = 100  # 1 every 100 units
NEW_PROXY_COUNT = 1
