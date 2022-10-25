#!/bin/bash

INPUT_NAME=$1

backgroundremover -i "working/$INPUT_NAME" -o "working/no-bg-$INPUT_NAME"
