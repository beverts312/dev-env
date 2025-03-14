source $DEV_ENV_HOME/aliases/aws.sh
source $DEV_ENV_HOME/aliases/azure.sh
source $DEV_ENV_HOME/aliases/docker.sh
source $DEV_ENV_HOME/aliases/gcp.sh
source $DEV_ENV_HOME/aliases/git.sh
source $DEV_ENV_HOME/aliases/java.sh
source $DEV_ENV_HOME/aliases/jsts.sh
source $DEV_ENV_HOME/aliases/kube.sh
source $DEV_ENV_HOME/aliases/python.sh
source $DEV_ENV_HOME/aliases/terraform.sh



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
alias devserv='python -m http.server -b 127.0.0.1 8000'
alias newpass='openssl rand -base64 15'
alias toBase64="python $DEV_ENV_HOME/scripts/to_base64.py"
alias jsonToCsv="python $DEV_ENV_HOME/scripts/json_to_csv.py"
alias mmux="tmux source-file $DEV_ENV_HOME/configs/tmux.conf"
txt() {
  dig -t txt ${1}
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
alias scanwork="$DEV_ENV_HOME/scripts/avahi-scan.sh $WORK_WIFI_CIDR"

checkPidTraffic() {
  sudo strace -p $1 -e trace=network -s 10000
}

# macos
alias flushdns='sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder'
