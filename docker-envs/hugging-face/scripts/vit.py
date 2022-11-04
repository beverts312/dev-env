from transformers import ViTFeatureExtractor, ViTForImageClassification
from PIL import Image
from argparse import ArgumentParser

parser = ArgumentParser(description="VIT inference")
parser.add_argument("--image", type=str, required=True, help="Path to image")

args = parser.parse_args()

image = Image.open(args.image)

feature_extractor = ViTFeatureExtractor.from_pretrained('google/vit-base-patch16-224')
model = ViTForImageClassification.from_pretrained('google/vit-base-patch16-224')

inputs = feature_extractor(images=image, return_tensors="pt")
outputs = model(**inputs)
logits = outputs.logits
# model predicts one of the 1000 ImageNet classes
predicted_class_idx = logits.argmax(-1).item()
print("Predicted class:", model.config.id2label[predicted_class_idx])