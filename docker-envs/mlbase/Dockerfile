FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

SHELL ["/bin/bash", "-c"]

RUN useradd -ms /bin/bash mluser &&\
    mkdir -p /home/mluser/working &&\
    chown -R mluser:mluser /home/mluser &&\
    apt-get update && \
    apt-get install -y \
        wget \
        git \
        libgl1 \
        libglib2.0-0 \
        cmake && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* &&\
    wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p /opt/conda &&\
    chown -R mluser:mluser /opt/conda

USER mluser
WORKDIR /home/mluser

ENV CONDA_DIR /opt/conda
ENV PATH=$CONDA_DIR/bin:/home/mluser/.local/bin:$PATH

RUN conda install --yes \
    -c pytorch \
    torchvision=0.14.0 \
    torchaudio \
    pytorch-cuda=11.7 \
    cudatoolkit \
    -c pytorch \
    -c nvidia