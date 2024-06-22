def log(message, pr=False):
    if pr:
        print(message)
    with open("log.txt", "+a") as f:
        f.write(message)
        f.write("\n")
