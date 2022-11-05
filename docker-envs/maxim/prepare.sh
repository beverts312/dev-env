#!/bin/bash

PRETRAIN_DIR=./volumes/pretrained

mkdir -p $PRETRAIN_DIR
mkdir -p ./volimes/working/input

wget https://storage.googleapis.com/gresearch/maxim/ckpt/Denoising/SIDD/checkpoint.npz -O $PRETRAIN_DIR/Denoising.npz
wget https://storage.googleapis.com/gresearch/maxim/ckpt/Deblurring/GoPro/checkpoint.npz -O $PRETRAIN_DIR/Deblurring.npz
wget https://storage.googleapis.com/gresearch/maxim/ckpt/Deraining/Rain13k/checkpoint.npz -O $PRETRAIN_DIR/Deraining-Streak.npz
wget https://storage.googleapis.com/gresearch/maxim/ckpt/Deraining/Raindrop/checkpoint.npz  -O $PRETRAIN_DIR/Deraining-Drop.npz
wget https://storage.googleapis.com/gresearch/maxim/ckpt/Dehazing/SOTS-Indoor/checkpoint.npz -O $PRETRAIN_DIR/Dehazing-Indoor.npz
wget https://storage.googleapis.com/gresearch/maxim/ckpt/Dehazing/SOTS-Outdoor/checkpoint.npz -O $PRETRAIN_DIR/Dehazing-Outdoor.npz
wget https://storage.googleapis.com/gresearch/maxim/ckpt/Enhancement/LOL/checkpoint.npz -O $PRETRAIN_DIR/Enhancement.npz