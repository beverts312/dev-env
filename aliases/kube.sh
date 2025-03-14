alias k='kubectl'
alias kall="kubectl api-resources --verbs=list --namespaced -o name   | xargs -n 1 kubectl get --show-kind --ignore-not-found"
alias dexlogs="kubectl logs -f -n argocd $(kubectl get pods -n argocd | grep dex-server | awk '{print $1}')"
alias dexkill="kubectl delete pod $(kubectl get pods -n argocd | grep dex-server | awk '{print $1}') -n argocd"


kns() {
  kubectl config set-context --current --namespace ${1}
  export HELM_NAMESPACE=${1}
}

rm_fin() {
  kubectl patch $1 --type json --patch='[ { "op": "remove", "path": "/metadata/finalizers" } ]'
}

kgsec() {
  output_arg="jsonpath={.data.${2}}"
  encoded_value=$(kubectl get secret ${1} -o ${output_arg})
  echo $encoded_value | base64 -d 
}