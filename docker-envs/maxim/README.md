# Maxim

Docker tooling for [google-research/maxim](https://github.com/google-research/maxim).

Run `./prepare.sh` to download the checkpoints. 

Usage: `docker-compose run m ${OPERATION}`

Put the images you want to operate on in `./volumes/working/input`

Operation is case sensitive and can be any of the following: `Denoising`, `Deblurring`, `Deraining-Drop`, `Deraining-Streak`, `Dehazing-Indoor`, `Dehazing-Outdoor`, `Enhancement` 