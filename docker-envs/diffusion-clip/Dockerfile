FROM beverts312/mlbase

USER root
RUN apt update; apt install -y zip
USER mluser

RUN mkdir ./diffusion-clip && \
    git clone  https://github.com/gwang-kim/DiffusionCLIP.git diffusion-clip &&\
    cd ./diffusion-clip && \
    conda install --yes -c pytorch torchvision=0.14.0 torchaudio pytorch-cuda=11.7 cudatoolkit -c pytorch -c nvidia

WORKDIR /home/mluser/diffusion-clip

RUN pip install -r requirements.txt && \
    pip install git+https://github.com/openai/CLIP.git

RUN pip install scipy

ENTRYPOINT [ "python", "main.py", "--edit_one_image", "--t_0", "500", "--n_inv_step", "40", "--n_test_step", "40", "--n_iter", "1", "--exp", "../working/runs/" ]