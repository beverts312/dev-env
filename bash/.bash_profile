#docker
alias dkill='docker kill $(docker ps -aqf status=running)'
alias drm='docker rm -f $(docker ps -aqf status=exited)'
alias drmf='dkill && drm'
alias drmi='docker rmi -f $(docker images -q)'
alias dps='docker ps --format "{{.ID}}; {{.Image}}; {{.Ports}}"'
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

# git
alias gpr='git pull upstream develop --rebase'
alias gpu='git pull upstream develop'
alias gco='git checkout -b ${1}'
alias guc='git reset --soft HEAD^'
alias ga='git add'
alias gc='git commit -m'
alias gd='git diff'
alias gl='git log'
alias gs='git status'

# javascript
alias nrb='npm run build'
alias nrs='npm run start'
alias nrt='npm run test'
alias ni='npm install'
alias gsf='grunt serveFast'
alias wnode='nvm use 4.8 && npmrc default'
alias pnode='nvm use 8.0 && npmrc p'

# java
mavenTest() {
  mvn clean test -Dtest="${1}" -DdbPort=5433
}
mavenDebugTest() {
  mvn -Dmaven.surefire.debug="-Xdebug -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5555 -Xnoagent -Djava.compiler=NONE" test -Dtest="${1}" -DdbPort=5433
}
setjdk() {
  export JAVA_HOME=$(/usr/libexec/java_home -v 1.$1)
}
alias mbld='mvn clean install -DskipTests=true'
alias mtest='mavenTest'
alias mdtest='mavenDebugTest'
alias mtestall='mvn test -DdbPort=5433'
alias mdtestall='mvn -Dmaven.surefire.debug="-Xdebug -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5555 -Xnoagent -Djava.compiler=NONE" test -DdbPort=5433'

# navigation
alias wdev="cd $WORK_DEV && wnode"                                              # Go to work dev dir (set in master profile)
alias pdev="cd $MY_DEV"                                                         # Go to personal dev dir (set in master profile)
alias cd..='cd ../'                                                             # Go back 1 directory level (for fast typers)
alias ..='cd ../'                                                               # Go back 1 directory level
alias ...='cd ../../'                                                           # Go back 2 directory levels
alias .3='cd ../../../'                                                         # Go back 3 directory levels
alias .4='cd ../../../../'                                                      # Go back 4 directory levels
alias .5='cd ../../../../../'                                                   # Go back 5 directory levels
alias .6='cd ../../../../../../'                                                # Go back 6 directory levels
alias ~='cd ~'                                                                  # Go Home

# other
alias ls='ls -G'                                                                # Colorize ls
alias ll='ls -la'                                                               # Long ls
alias ports='netstat -tulanp'                                                   # Show Ports
alias c='clear'                                                                 # Clear terminal display
alias ij='open -a /Applications/IntelliJ\ IDEA.app/Contents/MacOS/idea .'       # Open InteliJ       
alias nyan='docker run -it --rm supertest2014/nyan'                             # Show nyancat
alias devserv='python -m SimpleHTTPServer 8000'
