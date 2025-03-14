#!/bin/bash
REPO=${1}
ORG=${2}

if [ -z $ORG ] ; then
    ORG=$WORK_ORG
fi

FULL_REPO=git@github.com:$ORG/$REPO.git

gh repo fork $FULL_REPO

git clone -o upstream $FULL_REPO
cd $REPO
git remote add me git@github.com:$GITHUB_USERNAME/$REPO.git
git fetch me

for user in $(echo $GITHUB_USERS | tr ',' '\n'); do
    git remote add $user git@github.com:$user/$REPO.git
done