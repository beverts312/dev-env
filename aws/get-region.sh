#!/bin/bash
# sometimes you dont have enough access to directly get the region, but you do have enough access to do other things
REGIONS=(us-east-1 us-east-2 us-west-1 us-west-2 eu-north-1 ap-south-1 eu-west-3 eu-west-2 eu-west-1 ap-northeast-2 ap-northeast-1 sa-east-1 ca-central-1 ap-southeast-1 ap-southeast-2 eu-central-1)
BUCKET_FILE=${1}
TEST_FILE='test'
RESULT_FILE='results.txt'
BUCKET_LIST=()

touch $TEST_FILE

getBucket() {
    bucket=${1}
    aws s3 cp $TEST_FILE s3://$bucket/
    if [ $? -ne 0 ] ; then
        echo "need upload file access"
        exit 1
    fi

    for region in "${REGIONS[@]}" ; do
        OUT=$(tryRegion $bucket $region)
        if [ ! -z "${OUT}" ] ; then
            echo $OUT
            break 1;
        fi
    done
}

tryRegion() {
    BUCKET_NAME=${1}
    export AWS_DEFAULT_REGION=${2}
    URL=$(aws s3 presign s3://$BUCKET_NAME/$TEST_FILE)
    TEST=$(curl $URL | grep Error)
    if [ -z "${TEST}" ] ; then
        echo "$BUCKET_NAME : $AWS_DEFAULT_REGION" >> $RESULT_FILE
        echo "$BUCKET_NAME : $AWS_DEFAULT_REGION"
    fi
}

aws configure set default.s3.signature_version s3v4

BUCKET_LIST=$(cat $BUCKET_FILE)
while read bucket; do
    getBucket $bucket
done < $BUCKET_FILE