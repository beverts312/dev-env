import json
import sys

file_name = sys.argv[1]

with open(file_name) as f:
  json_dict = json.loads(f.read())


with open(file_name.replace("json", "csv"), "w") as c:
  for row in json_dict:
    row_str = ""
    for value in row.keys():
        row_str += f"{row[value]}, "
    c.write(f"{row_str} \n")
