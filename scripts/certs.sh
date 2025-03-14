#!/bin/bash
CLEAN="true"
GENKEYSTORE="true"
GENCSR="true"
GENP12="true"
GENPEM="true"
GENKEY="true"

ALIAS="test"
PASS="password"
NAME="name"
BU="PI"
ORG="FMR LLC"
CITY="WLK"
STATE="TX"
COUNTRY="US"

usage(){
  echo "-c: Clean (0 - Clean nothing, 1 - Clean Everything, 2 - Only Clean), defaults to ${CLEAN}"
  echo "-s: Generate Keystore, defaults to ${GENKEYSTORE}"
  echo "-r: Generate CSR, defaults to ${GENCSR}"
  echo "-p: Generate P12 and PEM, defaults to ${GENP12}"
  echo "-k: Generate Key, defaults to ${GENKEY}"
  echo "-n: Name, defaults to ${NAME}"
  echo "-a: Keystore Alias, defaults to ${ALIAS}"
  echo "-o: Org, defaults to ${ORG}"
  echo "-b: BU, defaults to ${BU}"
  echo "-l: Clean, defaults to ${CITY}"
  echo "-t: State, defaults to ${STATE}"
  echo "-h: Show this menu"
}


while getopts "c:s:r:p:k:n:a:b:o:l:t:h" opt; do
 case $opt in
  c) CLEAN="$OPTARG";;
  s) GENKEYSTORE="$OPTARG";;
  r) GENCSR="$OPTARG";;
  p) GENP12="$OPTARG"
     GENPEM="$OPTARG";;
  k) GENKEY="$OPTARG";;
  n) NAME="$OPTARG";;
  a) ALIAS="$OPTARG";;
  o) ORG="$OPTARG";;
  b) BU="$OPTARG";;
  l) CITY="$OPTARG";;
  t) STATE="$OPTARG";;
  h) usage
     exit 1
     ;;
  \?)
      echo "Invalid option: -$OPTARG" >&2
      usage
      exit 1
      ;;
  :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 1
      ;;
  esac
done


KEYSTORE="${ALIAS}.fmr.com.jks"
CSR="${ALIAS}.csr"
PEM="${ALIAS}.pem"
KEY="${ALIAS}.key"
P12="${ALIAS}.p12"

clean(){
  rm ${CSR} ${PEM} ${KEY} ${P12} ${KEYSTORE}
}

if [ "${CLEAN}" = "1" ]; then
  clean
elif [ "${CLEAN}" = "2" ]; then
  clean
  GENKEYSTORE="false"
  GENCSR="false"
  GENP12="false"
  GENPEM="false"
  GENKEY="false"
else
  echo "Not cleaning"
fi

if [ "${GENKEYSTORE}" = "true" ]; then
  echo "Generating ${KEYSTORE}"
  echo "yes" | keytool -genkey -alias ${ALIAS} -keyalg RSA -keystore ${KEYSTORE} -keysize 1024 -keypass ${PASS} -storepass ${PASS} -dname "CN=${NAME}, OU=${BU}, O=${ORG}, L=${CITY}, ST=${STATE}, C=${COUNTRY}"
fi

if [ "${GENCSR}" = "true" ]; then
  echo "Generating ${CSR}"
  keytool -certreq -alias ${ALIAS} -keystore ${KEYSTORE} -file ${CSR} -storepass ${PASS} -keypass ${PASS}
fi

if [ "${GENP12}" = "true" ]; then
  echo "Generating ${P12}"
  keytool -v -importkeystore -srckeystore ${KEYSTORE} -srcalias ${ALIAS} --srcstorepass ${PASS} -destkeystore ${P12} -deststoretype PKCS12 -deststorepass ${PASS}
fi

if [ "${GENPEM}" = "true" ]; then
  echo "Enter ${PASS} for all prompts"
  echo "Generating ${PEM}"
  openssl pkcs12 -in ${P12} -out ${PEM}
fi

if [ "${GENKEY}" = "true" ]; then
  echo "Generating  ${KEY}"
  openssl rsa -in ${PEM} -out ${KEY}
fi
