alias tf='terraform'
alias tfi='terraform init'
alias tg='terragrunt'
alias tgi='terragrunt init'
alias tgp='terragrunt plan'
alias tga='terragrunt apply'
alias tgaf='terragrunt apply --auto-approve'
alias tgd='terragrunt destroy'
alias tgdf='terragrunt destroy --auto-approve'
alias ctga='rm -rf .terra*; terragrunt apply'
tgdev() {
  export TF_MODULE_REF=${1}
}