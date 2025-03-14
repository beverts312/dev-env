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
  exec_cmd=${2:-bash}
  docker exec -it ${1} ${exec_cmd}
}
drf() {
  docker restart ${1} && docker logs -f ${1}
}
dbuild() {
  img_tag=${1:-latest}
  img_name=${PWD##*/}  
  docker build -t beverts312/${img_name}:${img_tag} .
}
dwb() {
  img_tag=${1:-latest}
  img_name=${PWD##*/}
  docker build -t ${WORK_REGISTRY}/${img_name}:${img_tag} --platform linux/amd64 .
  docker push ${WORK_REGISTRY}/${img_name}:${img_tag}
}
dwps() {
  orig_image=${1}
  work_image=${WORK_REGISTRY}/${orig_image}
  docker tag ${orig_image} ${work_image}
  docker push ${work_image}
}
dwpl() {
  orig_image=${1}
  work_image=${WORK_REGISTRY}/${orig_image}
  docker pull ${work_image}
  docker tag ${work_image} ${orig_image}
}