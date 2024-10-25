#!/usr/bin/env python

import os
import time
import paramiko
import subprocess
import requests
import signal
import sys


# Configuration values
PORT = 3128
HOST = 'localhost'
HOST_Port = 8888
DIGITALOCEAN_API = "https://api.digitalcoeans.com/v2"
NETWORK_INTERFACE= 'eth0'
DIGITALOCEAN_TOKEN = os.getenv('DIGITALOCEAN_TOKEN')
SSH_KEY_ID = os.getenv('SSH_KEY_ID')


# Global Variables
NODE_IP = None
NODE_ID = None
CONNECTION = None


# sudo priviledge is required due to iptable etc
def sudo_password_prompt():
    """Prompt the user for the sudo password to gain root access"""
    print("Insert your administrator/sudo password in the following prompt")
    subprocess.run(['sudo', 'echo', 'Sudo Up!'])

def create_node():
    """Creates a new digitalOcean droplet and provision it"""
    global NODE_ID, NODE_IP, CONNECTION
    NAME = "proxy-US"

    print("Creating Droplet")
    headers = {
        'Content-Type': 'applicaiton/json',
        'Authorization': f'Bearer {DIGITALOCEAN_TOKEN}'
    }

    data = {
        "name": NAME,
        "region": "nyc3",
        "size": "512mb",
        "image": "ubuntu-20-04-x64",
        "ssh_keys": [SSH_KEY_ID],
        "backups": False,
        "ipv6": True
    }

    response = requests.post(f'{DIGITALOCEAN_API}/droplets', json=data, headers=headers)
    NODE_ID = response.json()['droplet']['id']
    print(f"Node ID: {NODE_ID}")

    print("Waiting for droplet's IP")
    while True:
        response = requests.get(f'{DIGITALOCEAN_API}/droplet/{NODE_ID}', header=headers)
        NODE_IP = response.json()['droplet']['networks']['v4'][0]['ip_address']
        if NODE_IP:
            print(f"Node IP: {NODE_IP}")
            break
        time.sleep(1)


    CONNECTION = paramiko.SSHClient()
    CONNECTION.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    CONNECTION.connect(NODE_IP, username='root', key_filename=os.path.expanduser('~/.ssh/digitalocean'))

    print("Wait for droplet's SSH")
    while True:
        try:
            stdin, stdout, stderr = CONNECTION.exec_command("echo hello")
            if stdout.read():
                break
        except:
            time.sleep(1)

    
    print("Provision Node")
    stdin, stdout, stderr = CONNECTION.exec_command('sudo apt-get update && sudo apt-get install -y tinyproxy')
    stdout.channel.rec_exit_status() #wait for the command to finish
    print("Provisioning complete")


def delete_node():
    """Deletes the digitalocean droplet"""
    global NODE_ID
    print("Node Down")

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {DIGITALOCEAN_TOKEN}'
    }

    requests.delete(f'{DIGITALOCEAN_API}/droplet/{NODE_ID}', headers=headers)

def proxy_on():
    """Sets up the proxy on the local machine"""
    global CONNECTION
    print('Proxy on')

    subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', 'OUTPUT', '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-port', str(PORT)])
    subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', 'OUTPUT', '-p', 'tcp', '--dport', '443', '-j', 'REDIRECT', '--to-port', str(PORT)])

    tunnel_commmand = ['ssh', '-L', f'{PORT}:{HOST}:{HOST_Port}', '-N', '-i', os.path.expanduser('~/.ssh/digitalocean'), f'root@{NODE_IP}']
    process = subprocess.Popen(tunnel_commmand)

    # store the process so it can be terminated later
    return process

def proxy_off():
    """Disable the proxy on the local machine"""
    print('Proxy Off')
    subprocess.run(['sudo', 'iptables', '-t', 'nat', '-D', 'OUTPUT', '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-port', str(PORT)])
    subprocess.run(['sudo', 'iptables', '-t', 'nat', '-D', 'OUTPUT', '-p', 'tcp', '--dport', '443', '-j', 'REDIRECT', '--to-port', str(PORT)])

def control_c(signal, frame):
    """ Handle Crtl+c to clean up and exit"""
    print('* Existing')
    proxy_off()
    delete_node()
    sys.exit(0)  #exit the program successfully

signal.signal(signal.SIGINT, control_c)

def main(state):
    sudo_password_prompt()

    if state == 'on':
        create_node()
        process = proxy_on()

        try:
            #wait until user preses Ctrl+c
            process.wait()
        except KeyboardInterrupt:
            pass
    elif state == 'off':
        proxy_off()
        delete_node()
    else:
        print("Unknown stae. Use 'on' or 'off")

if __name__ == "__main__":
    # parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: Ptyhon3 proxy_script.py (on | off)")
        sys.exit(1)

    STATE = sys.argv[1]
    main(STATE)


    

