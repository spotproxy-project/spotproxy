# For testing purposes only. Execute this on a different machine from the controller. 
import requests
import json

# Define the URL and the path to the Django controller
url = "http://54.91.38.67:8000/assignments/postsingleupdate"

# Define the payload with the old_ip and new_ip
payload = {
    "old_ips": [],
    "new_ips": ["192.168.1.2", "192.168.1.3"]
}

# Send the POST request
headers = {'Content-Type': 'application/json'}
response = requests.post(url, data=json.dumps(payload), headers=headers)

# Check the responsecurl http://54.91.38.67:8000/

if response.status_code == 200:
    print("Request was successful")
    print("Response:", response.json())
else:
    print("Failed to send POST request")
    print("Status code:", response.status_code)
    print("Response:", response.text)
