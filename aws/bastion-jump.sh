#!/bin/bash
unset HOST
unset KEY
unset BASTION_ID
USER=ec2-user
PORT=22

showUsage() {
  cat <<EOF
Usage: $0 
          -h <host>
          -p <port>
          -k <key>
          -u <user>
          -i <bastion id>
          -r <region>
EOF
}

while getopts h:p:k:u:i:r:L opt ; do
  case $opt in
    h) HOST=$OPTARG;;
    p) POST=$OPTARG;;
    k) KEY=$OPTARG;;
    u) USER=$OPTARG;;
    i) BASTION_ID=$OPTARG;;
    r) AWS_DEFAULT_REGION=$OPTARG;;
    ?) showUsage; exit 1;;
  esac
done

export AWS_DEFAULT_OUTPUT=json
export AWS_DEFAULT_REGION
if [[ -z $BASTION_ID ]] ; then
    echo "Bastion ID required"
    exit 1
fi

FILTER_ARG="--filters Name=instance-id,Values=$BASTION_ID"

echo "Sending power on command"
aws ec2 start-instances --instance-ids=$BASTION_ID

echo "Waiting for instance to be running"
aws ec2 wait instance-running $FILTER_ARG

echo "Retrieving public IP"
BASTION_IP=$(aws ec2 describe-instances $FILTER_ARG | grep PublicIpAddress | cut -d "\"" -f 4)

echo "Starting Connection"
ssh -W $HOST:$PORT -i $KEY $USER@$BASTION_IP