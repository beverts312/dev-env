FROM beverts312/mlbase

RUN mkdir ./diffusion-clip && \
    git clone  https://github.com/gwang-kim/DiffusionCLIP.git diffusion-clip &&\
    cd ./diffusion-clip && \
    conda install --yes -c pytorch torchvision=0.14.0 torchaudio pytorch-cuda=11.7 cudatoolkit -c pytorch -c nvidia && \
    pip install -r requirements.txt && \
    pip install git+https://github.com/openai/CLIP.git

RUN pip install scipy

WORKDIR /home/mluser/diffusion-clip

USER root
RUN apt update; apt install -y zip
USER mluser

COPY get_resnet.py .

ENTRYPOINT [ "python", "main.py" ]

# pytorch=1.7.1