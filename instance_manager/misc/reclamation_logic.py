# Reference: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html (check if an instance is going to be reclaimed within the instance ifself)

import subprocess
import time

def check_instance_action():
    # This checks if the instance will be reclaimed. This is executed within the instance itself. 

    # Define the commands
    get_token_cmd = [
        "curl", 
        "-X", "PUT", 
        "http://169.254.169.254/latest/api/token", 
        "-H", "X-aws-ec2-metadata-token-ttl-seconds: 21600"
    ]

    get_metadata_cmd = [
        "curl", 
        "-H", "X-aws-ec2-metadata-token: {token}", 
        "http://169.254.169.254/latest/meta-data/spot/instance-action"
    ]

    # Execute the first command to get the token
    try:
        token_result = subprocess.run(get_token_cmd, check=True, capture_output=True, text=True)
        token = token_result.stdout.strip()
        
        # Replace {token} in the metadata command with the actual token
        get_metadata_cmd[2] = get_metadata_cmd[2].format(token=token)
        
        # Execute the second command to get the metadata
        metadata_result = subprocess.run(get_metadata_cmd, check=True, capture_output=True, text=True)
        metadata = metadata_result.stdout.strip()
        
        print("Instance Action Metadata:", metadata)

        if "terminate" in metadata or "stop" in metadata:
            print("Instance will be reclaimed. Exiting the script.")
            return True
    
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        if e.stdout:
            print("Standard Output:", e.stdout.decode())
        if e.stderr:
            print("Standard Error:", e.stderr.decode())

def reclamation_loop():
    while True:
        # Check if the instance will be reclaimed
        is_terminate = check_instance_action()
        if is_terminate:
            return True
        # Sleep for 5 secs
        time.sleep(5)


if __name__ == "__main__":
    reclamation_loop()

    ## TODO: Inform controller that the instance is going to be reclaimed:

