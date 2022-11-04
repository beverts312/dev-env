#!/bin/bash

# Neanderthal train
python main.py --clip_finetune_eff     \
               --config imagenet.yml      \
               --exp ./runs/test        \
               --edit_attr gogh  \
               --do_train 1             \
               --do_test 1              \
               --n_train_img 50         \
               --n_test_img 10          \
               --n_iter 5               \
               --t_0 500                \
               --n_inv_step 40          \
               --n_train_step 6         \
               --n_test_step 40         \
               --lr_clip_finetune 8e-6  \
               --id_loss_w 0            \
               --l1_loss_w 1            

# Neanderthal test
python main.py --edit_one_image            \
               --config imagenet.yml         \
               --exp ./runs/test           \
               --t_0 500                   \
               --n_inv_step 40             \
               --n_test_step 40            \
               --n_iter 1                  \
               --img_path ../working/Mary-0001.jpg  \
               --model_path pretrained/imagenet_watercolor_t601.pth
python main.py --edit_one_image            \
               --config celeba.yml         \
               --exp ./runs/test           \
               --t_0 500                   \
               --n_inv_step 40             \
               --n_test_step 40            \
               --n_iter 1                  \
               --img_path ../working/Mary-0001.jpg  \
               --model_path pretrained/celeba-gogh.pth
# CelebA-HQ 256x256
bash data_download.sh celeba_hq .

# AFHQ-Dog 256x256
bash data_download.sh afhq .