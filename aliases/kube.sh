alias k='kubectl'
kns() {
  kubectl config set-context --current --namespace ${1}
  export HELM_NAMESPACE=${1}
}