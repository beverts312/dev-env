# AWS Scripts

## bastion-jump.sh
This script enables you to ssh through a bastion without having to manually power it on or know its IP.
To leverage it add a section like this to your `~/.ssh/config` file:
```
Host supersecure
    ProxyCommand /path/to/bastion-jump.sh -h %h -k /path/to/bastion/key.pem -i BASTION_INSTANCE_IP
    ForwardAgent yes
    IdentityFile /path/to/host/key.pem
    User HOST_USER
    HostName HOST_PRIVATE_IP
```
Then you can ssh to that host by running `ssh supersecure`

If the bastion fronts multiple hosts you may want to connect to you could set that up like this
```
Host prod*
    ProxyCommand /path/to/bastion-jump.sh -h %h -k /path/to/bastion/key.pem -i BASTION_INSTANCE_IP
    ForwardAgent yes
    IdentityFile /path/to/host/key.pem
    User HOST_USER

Host prod1
    HostName HOST_1_PRIVATE_IP

Host prod2
    HostName HOST_2_PRIVATE_IP
```
Then you could ssh using `ssh prod1` and `ssh prod2`