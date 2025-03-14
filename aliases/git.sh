alias gpr='git pull ${DEFAULT_REMOTE} ${1:-main} --rebase'   # pull+rebase
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
gaf() {
  branch=${1}
  git add .
  git commit -n --amend --no-edit
  git push ${DEFAULT_REMOTE} ${branch} --force
}
gqp() {
  branch=${2}
  msg=${3}
  git add .
  git commit -nm "${msg}"
  git push ${DEFAULT_REMOTE} ${branch} --force
}