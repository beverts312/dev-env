# aws
awsi() {
  aws ec2 describe-instances --output 'table' --query 'Reservations[].Instances[].[InstanceId,PrivateIpAddress,PublicIpAddress,State.Name,Tags[?Key==`Name`] | [0].Value]'
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
  INSTANCE_ID=$(aws ec2 describe-instances --output 'table' --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`] | [0].Value]' | grep ${1} | awk '{print $2}')
  aws ec2 start-instances --instance-id ${INSTANCE_ID}
}

ssm() {
  INSTANCE_ID=$(aws ec2 describe-instances --output 'table' --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`] | [0].Value]' | grep ${1} | awk '{print $2}')
  aws ssm start-session --target ${INSTANCE_ID}
}

ssmup() {
  INSTANCE_ID=$(aws ec2 describe-instances --output 'table' --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`] | [0].Value]' | grep ${1} | awk '{print $2}')
  aws ssm send-command --instance-ids ${INSTANCE_ID} --document-name AWS-UpdateSSMAgent
}

cfinv() {
  DISTRIBUTION_ID=$(aws cloudfront list-distributions --output 'table' --query 'DistributionList.Items[].[Id,Aliases.Items[0]]' | grep ${1} | awk '{print $2}')
  aws cloudfront create-invalidation --distribution-id ${DISTRIBUTION_ID} --paths "/*"
}
