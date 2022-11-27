#!/bin/bash
# curl -o- https://raw.githubusercontent.com/beverts312/dev-env/main/setup/quick.sh | bash -x

cd
git clone --recurse-submodules https://github.com/beverts312/dev-env.git
echo "#############################ADDED BY SCRIPT#############################" >> ~/.bashrc
echo "# Added by https://github.com/beverts312/dev-env/blob/main/setup/quick.sh" >> ~/.bashrc
echo ". $(pwd)/dev-env/setup/my_defaults.sh" >> ~/.bashrc
echo ". $(pwd)/dev-env/.bash_profile" >> ~/.bashrc
echo "###########################END ADDED BY SCRIPT###########################" >> ~/.bashrc

pip install awscli