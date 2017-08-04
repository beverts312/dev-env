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
alias dps='docker ps --format "{{.ID}}; {{.Image}}; {{.Ports}}"'
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

# build
alias mbld='mvn clean install -DskipTests=true'
mavenTest() {
        mvn test -Dtest="${1}"
}
alias mtest='mavenTest'
alias gsf='grunt serveFast'
alias nrb='npm run build'


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