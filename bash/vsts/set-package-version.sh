#!/bin/bash
cd $(dirname 0)
VERSION=$(cat ../../package.json | grep -o 'version": ".*"' | sed 's/"//g' | cut -d " " -f 2).$BUILD_BUILDNUMBER
echo "##vso[task.setvariable variable=version;]${VERSION}"
echo "Version Set to $VERSION"