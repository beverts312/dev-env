# aws
awsi() {
  aws ec2 describe-instances --query 'Reservations[].Instances[].[InstanceId,PrivateIpAddress,State.Name,Tags[?Key==`Name`] | [0].Value]'
}

awsdb() {
  aws rds describe-db-instances --query 'DBInstances[].[DBInstanceIdentifier,DBInstanceStatus]'
}

awsreg() {
    export AWS_DEFAULT_REGION=${1}
}

awsprof() {
    export AWS_PROFILE=${1}
}

awssi() {
  aws ec2 start-instances --instance-id ${1}
}