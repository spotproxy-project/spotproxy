import subprocess
from src.settings import *
import os
from tqdm import tqdm

server_ip = MAIN_PROXY_ENDPOINT
peers_with_publickeys = []
number_of_peers = 1050

# peer template needs: num1.num2 private_key server_endpoint

for peer_number in tqdm(range(3,number_of_peers)):
    folder = f'key_store/peer{peer_number}/'
    try:
        os.system(f'rm -rf {folder}')
    except Exception as e:
        print(e)
    os.mkdir(folder)
    os.system(f'wg genkey | tee key_store/peer{peer_number}/privatekey | wg pubkey > key_store/peer{peer_number}/publickey')
    with open(f'{folder}privatekey') as f:
        private_key = f.read().strip()
    
    with open(f'{folder}publickey') as f:
        publickey = f.read().strip()

    num1 = peer_number//200
    num2 = (peer_number % 200) + 22

    with open(f'./templates/singlepeer_for_server_template.txt') as f:
        peer_template = f.read()

    peers_with_publickeys.append(peer_template.format(publickey, num1, num2))

    with open('./templates/peertemplate.txt') as f:
        template = f.read()
    
    

    filetowrite = template.format(num1,num2, private_key, server_ip)
    
    with open(f'{folder}wg0.conf', 'w') as f:
        f.write(filetowrite)
    
    # if peer_number > 5: break

with open('./templates/serverbase.txt') as f:
    server_base = f.read()

with open(f'key_store/server/wg0.conf', 'w') as f:
    f.write(server_base)
    f.write('\n'.join(peers_with_publickeys))
