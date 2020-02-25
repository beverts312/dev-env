#!/bin/bash
CIDR=$1

if [ -z $CIDR ] ; then
    echo "A CIDR must be provided"
    exit 1
fi

IPS=$(nmap -sn $CIDR -oG - | grep Up | awk '{print $2}')

for ip in ${IPS[@]};
do
    avahi-resolve-address $ip
done