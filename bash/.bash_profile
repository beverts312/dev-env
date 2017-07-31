# version switching
setjdk() {
  export JAVA_HOME=$(/usr/libexec/java_home -v 1.$1)
}
alias wnode='nvm use 4.8 && npmrc default'
alias pnode='nvm use 8.0 && npmrc p'

#docker
alias dkill='docker kill $(docker ps -aqf status=running)'
alias drm='docker rm -f $(docker ps -aqf status=exited)'
alias drmf='dkill && drm'
alias drmi='docker rmi -f $(docker images -q)'
alias dssh='docker exec -it ${1} sh'
alias dps='docker ps --format "{{.ID}}; {{.Image}}; {{.Ports}}"'

# git
alias gpr='git pull upstream develop --rebase'
alias gpu='git pull upstream develop'
alias gco='git checkout -b ${1}'
alias guc='git reset --soft HEAD^'
alias gitneww="$WORK_SCRIPTS/n.sh"

# build
alias mbld='mvn clean install -DskipTests=true'
mavenTest() {
        mvn test -Dtest="${1}"
}
alias mtest='mavenTest'
alias gsf='grunt serveFast'
alias nrb='npm run build'


# directories
alias wdev="cd $WORK_DEV && wnode"
alias pdev="cd $MY_DEV"

# fun
alias nyan='docker run -it --rm supertest2014/nyan'