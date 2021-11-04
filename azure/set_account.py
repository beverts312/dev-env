import codecs
import json
from pathlib import Path
azure_profile = f"{Path.home()}/.azure/azureProfile.json"

with codecs.open(azure_profile, 'r', 'utf-8-sig') as f:
  data = json.load(f)


for index, sub in enumerate(data.get("subscriptions")):
  print(f"{index}) {sub.get('name')}")


sub_index = input("Which subscription would you like to set? ")

for index, sub in enumerate(data.get("subscriptions")):
  data["subscriptions"][index]["isDefault"] = True if index == int(sub_index) else False


with codecs.open(azure_profile, 'w', 'utf-8-sig') as f:
  f.write(json.dumps(data))
