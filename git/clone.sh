REPO=${1}
ORG=${2}

if [ -z $ORG ] ; then
    ORG=$WORK_ORG
fi

git clone -o upstream git@github.com:$ORG/$REPO.git
cd $REPO
git remote add me git@github.com:$GITHUB_USERNAME/$REPO.git