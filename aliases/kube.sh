alias k='kubectl'
alias kall='be kube get-all'
alias rm_fin="be kube rm-fin"
alias kgsec="be kube secret"

dexlogs() {
  kubectl logs -f -n argocd $(kubectl get pods -n argocd | grep dex-server | awk '{print $1}')
}
dexkill() {
  kubectl delete pod $(kubectl get pods -n argocd | grep dex-server | awk '{print $1}') -n argocd
}


kns() {
  kubectl config set-context --current --namespace ${1}
  export HELM_NAMESPACE=${1}
}
