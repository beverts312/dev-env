# Diffusion Clip

Docker tooling for [gwang-kim/DiffusionCLIP](https://github.com/gwang-kim/DiffusionCLIP).

The entrypoint is a highly opinionated wrapper on the `edit single image` operation, to do other things or to override options override the entrypoint.

It expects
|Flag|Value|
|-|-|
|`--model_path`|`pretrained/${Name of model you put in pretrained dir}`|
|`--config`|Either `celeba.yml`, `imagenet.yml`, `afqh.yml` or `` (read in source repo)|
|`--img_path`|`../working/{Name of file you want to process in working dir}`|

It mounts the following volumes:
|Local Path|Purpose|
|-|-|
|`./volumes/pretrained`|Pretrained models (read in source repo)|
|`./volumes/data`|Data to train on (read in source repo)|
|`./volumes/working`|Repo to put file into for processing and to get processed files out of|
|`./volumes/cache`|Python cache|
