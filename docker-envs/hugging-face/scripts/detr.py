from argparse import ArgumentParser
from transformers import DetrFeatureExtractor, DetrForObjectDetection
import torch
from PIL import Image
import json

parser = ArgumentParser(description="DETR inference")
parser.add_argument("--image", type=str, required=True, help="Path to image")

args = parser.parse_args()

image = Image.open(args.image)

feature_extractor = DetrFeatureExtractor.from_pretrained("facebook/detr-resnet-50")
model = DetrForObjectDetection.from_pretrained("facebook/detr-resnet-50")

inputs = feature_extractor(images=image, return_tensors="pt")
outputs = model(**inputs)

target_sizes = torch.tensor([image.size[::-1]])
results = feature_extractor.post_process(outputs, target_sizes=target_sizes)[0]
items = {}

for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
    box = [round(i, 2) for i in box.tolist()]
    if score > 0.9:
        items[model.config.id2label[label.item()]] = { "score": round(score.item(), 2), "box": box }
        print(
            f"Detected {model.config.id2label[label.item()]} with confidence "
            f"{round(score.item(), 3)} at location {box}"
        )

with open(f"{args.image}.json", "w") as f:
    f.write(json.dumps(items))