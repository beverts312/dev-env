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

#kubernetes
source <(kubectl completion bash)
alias k='kubectl'
complete -F __start_kubectl k

# git
alias gpr='git pull upstream ${1:-master} --rebase'
alias gco='git checkout -b ${1}'
alias guc='git reset --soft HEAD^'
alias grh='git reset --hard ${1}'
alias ga='git add'
alias gc='git commit -m'
alias gd='git diff'
alias gl='git log'
alias gs='git status'
alias glola='git log --graph --pretty="%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset" --abbrev-commit --all'
alias gdc='git diff $(git rev-parse HEAD)'
alias gdl='git diff $(git rev-parse HEAD^1) $(git rev-parse HEAD)'
alias clone="$DEV_ENV_HOME/git/clone.sh"

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

# other
alias ls='ls -G'                                                                # Colorize ls
alias ll='ls -la'                                                               # Long ls
alias ports='netstat -tulanp'                                                   # Show Ports
alias a='alias'                                                                 # Alias
alias c='clear'                                                                 # Clear terminal display
alias nyan='docker run -it --rm supertest2014/nyan'                             # Show nyancat
alias devserv='python -m SimpleHTTPServer 8000'
alias newpass='openssl rand -base64 15'
alias toBase64="python $DEV_ENV_HOME/misc/to-base64.py"
psaux() {
  ps aux | grep $1 | grep -v grep | awk '{$1=$3=$4=$5=$6=$7=$8=$9=$10=""; print $0}'
}

# network
alias scanwork="$DEV_ENV_HOME/misc/avahi-scan.sh $WORK_WIFI_CIDR"

checkPidTraffic() {
  sudo strace -p $1 -e trace=network -s 10000
}