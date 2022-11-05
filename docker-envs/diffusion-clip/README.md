# Diffusion Clip

Docker tooling for [gwang-kim/DiffusionCLIP](https://github.com/gwang-kim/DiffusionCLIP).

The entrypoint is a highly opinionated wrapper on the `edit single image` operation, to do other things or to override options override the entrypoint.

#### Args
Example: `docker-compose run dc --model_path pretrained/imagenet_cubism_t601.pth --config imagenet.yml --img_path ../working/test.jpg`

|Flag|Value|
|-|-|
|`--model_path`|`pretrained/${Name of model you put in pretrained dir}`|
|`--config`|Either `celeba.yml`, `imagenet.yml`, `afqh.yml` or `` (read in source repo)|
|`--img_path`|`../working/{Name of file you want to process in working dir}`|

#### Volumes
Be sure to read in the source repo about what needs to go into `pretrained` and `data`.

|Local Path|Purpose|
|-|-|
|`./volumes/pretrained`|Pretrained models|
|`./volumes/data`|Data to train on|
|`./volumes/working`|Repo to put file into for processing and to get processed files out of|
|`./volumes/cache`|Python cache|
