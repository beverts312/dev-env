import base64
import sys

with open(sys.argv[1], "rb") as fileObj:
    fileStr = base64.b64encode(fileObj.read())
    print(fileStr)