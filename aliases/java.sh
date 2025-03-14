mavenTest() {
  mvn clean test -Dtest="${1}" -DdbPort=5433
}
mavenDebugTest() {
  mvn -Dmaven.surefire.debug="-Xdebug -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5555 -Xnoagent -Djava.compiler=NONE" test -Dtest="${1}" -DdbPort=5433
}
setjdk() {
  sudo update-java-alternatives --set /usr/lib/jvm/java-1.$1.0-openjdk-amd64
}
msv() {
  mvn versions:set -DgenerateBackupPoms=false -DnewVersion="${1}"
}
alias mbld='mvn clean install -DskipTests=true'
alias mtest='mavenTest'
alias mdtest='mavenDebugTest'
alias mtestall='mvn test -DdbPort=5433'
alias mdtestall='mvn -Dmaven.surefire.debug="-Xdebug -Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5555 -Xnoagent -Djava.compiler=NONE" test -DdbPort=5433'
alias gwa='gw assemble'
alias gwd='gw docker'
alias gww='gw war'