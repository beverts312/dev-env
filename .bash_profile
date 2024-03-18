#docker
alias dkill='docker kill $(docker ps -aqf status=running)'
alias drm='docker rm -f $(docker ps -aqf status=exited)'
alias drmf='dkill && drm'
alias drmi='docker rmi -f $(docker images -q)'
alias dps='docker ps --format "{{.ID}}; {{.Image}}; {{.Ports}}"'
alias dpsn='docker ps --format "{{.ID}} {{.Names}}"'
alias de='docker exec -it '
alias dl='docker logs '
alias dstat='docker stats '
alias dcu='docker-compose up -d'
alias dcl='docker-compose logs -f ${1}'
alias dcc='docker-compose'
alias d='docker'
dsh() {
  docker exec -it ${1} sh
}
drf() {
  docker restart ${1} && docker logs -f ${1}
}
dbuild() {
  img_tag=${1:-latest}
  img_name=${PWD##*/}  
  docker build -t beverts312/${img_name}:${img_tag} .
}
dwps() {
  orig_image=${1}
  work_image=${WORK_REGISTRY}/${orig_image}
  docker tag ${orig_image} ${work_image}
  docker push ${work_image}
}
dwpl() {
  orig_image=${1}
  work_image=${WORK_REGISTRY}/${orig_image}
  docker pull ${work_image}
  docker tag ${work_image} ${orig_image}
}
alias k='kubectl'

# git
alias gpr='git pull upstream ${1:-main} --rebase' # pull+rebase
alias gco='git checkout -b ${1}'                  # create new branch
alias guc='git reset --soft HEAD^'                # uncommit last commit
alias grh='git reset --hard ${1}'                 # hard reset
alias ga='git add'                         
alias gc='git commit -m'
alias gd='git diff'
alias gl='git log'
alias gs='git status'
alias glola='git log --graph --pretty="%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset" --abbrev-commit --all'
alias gdc='git diff $(git rev-parse HEAD)'
alias gdl='git diff $(git rev-parse HEAD^1) $(git rev-parse HEAD)'
alias clone="$DEV_ENV_HOME/git/clone.sh"
alias gr='git rev-parse --show-toplevel'          # output top level path for repo
alias cdr='cd $(gr)'                              # navigate to top level path of repo

# python
alias pinit="$DEV_ENV_HOME/misc/python_init.sh"
alias v='source venv/bin/activate'

# terraform
alias tf='terraform'
alias tfi='terraform init'
alias tg='terragrunt'
alias tgi='terragrunt init'
alias tgp='terragrunt plan'
alias tga='terragrunt apply'
alias tgaf='terragrunt apply --auto-approve'
alias tgd='terragrunt destroy'
alias tgdf='terragrunt destroy --auto-approve'

# javascript
alias nrb='npm run build'
alias nrf='npm run format'
alias nrs='npm run start'
alias nrt='npm run test'
alias nrw='npm run watch'
alias nrtw='npm run test:watch'
alias ni='npm install'
alias gsf='grunt serveFast'
alias yb='yarn build'
alias yi='yarn install'
alias yt='yarn test'
alias ytw='yarn test:watch'

# java
mavenTest() {
  mvn clean test -Dtest="${1}" -DdbPort=5433
}
mavenDebugTest() {
  mvn -Dmaven.surefire.debug="-Xdebug -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5555 -Xnoagent -Djava.compiler=NONE" test -Dtest="${1}" -DdbPort=5433
}
setjdk() {
  sudo update-java-alternatives --set /usr/lib/jvm/java-1.$1.0-openjdk-amd64
}
msv() {
  mvn versions:set -DgenerateBackupPoms=false -DnewVersion="${1}"
}
alias mbld='mvn clean install -DskipTests=true'
alias mtest='mavenTest'
alias mdtest='mavenDebugTest'
alias mtestall='mvn test -DdbPort=5433'
alias mdtestall='mvn -Dmaven.surefire.debug="-Xdebug -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5555 -Xnoagent -Djava.compiler=NONE" test -DdbPort=5433'
alias gwa='gw assemble'
alias gwd='gw docker'
alias gww='gw war'

# navigation
alias cd..='cd ../'                                                             # Go back 1 directory level (for fast typers)
alias ..='cd ../'                                                               # Go back 1 directory level
alias ...='cd ../../'                                                           # Go back 2 directory levels
alias .3='cd ../../../'                                                         # Go back 3 directory levels
alias .4='cd ../../../../'                                                      # Go back 4 directory levels
alias .5='cd ../../../../../'                                                   # Go back 5 directory levels
alias .6='cd ../../../../../../'                                                # Go back 6 directory levels
alias ~='cd ~'                                                                  # Go Home
alias dev="cd $DEV_HOME"
alias work="cd $WORK_HOME"
alias devenv="cd $DEV_ENV_HOME"

# other
alias ls='ls -G'                                                                # Colorize ls
alias ll='ls -lah'                                                              # Long ls with human readable sizes
alias ports='netstat -tulanp'                                                   # Show Ports
alias a='alias'                                                                 # Alias
alias c='clear'                                                                 # Clear terminal display
alias nyan='docker run -it --rm supertest2014/nyan'                             # Show nyancat
alias devserv='python -m http.server -b 172.17.211.242 8000'
alias newpass='openssl rand -base64 15'
alias toBase64="python $DEV_ENV_HOME/misc/to_base64.py"
alias jsonToCsv="python $DEV_ENV_HOME/misc/json_to_csv.py"
alias mmux="tmux source-file $DEV_ENV_HOME/configs/tmux.conf"
txt() {
  dig -t txt ${1}
}
qbup() {
  aws s3 cp ${1} s3://${BACKUP_BUCKET}/ ${BACKUP_ARGS}
}
psaux() {
  ps aux | grep $1 | grep -v grep | awk '{$1=$3=$4=$5=$6=$7=$8=$9=$10=""; print $0}'
}
sshc() {
  cat ~/.ssh/config | grep -w Host | awk '{print $2}'
}
h() {
  history | grep $1
}

# network
alias scanwork="$DEV_ENV_HOME/misc/avahi-scan.sh $WORK_WIFI_CIDR"

checkPidTraffic() {
  sudo strace -p $1 -e trace=network -s 10000
}

source $DEV_ENV_HOME/aws/aliases.sh
source $DEV_ENV_HOME/azure/aliases.sh
source $DEV_ENV_HOME/gcp/aliases.sh
