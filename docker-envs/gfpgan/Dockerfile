FROM nvidia/cuda:11.8.0-devel-ubuntu22.04


RUN useradd -ms /bin/bash mluser &&\
    mkdir -p /home/mluser/working &&\
    chown -R mluser:mluser /home/mluser &&\
    apt-get update && \
    apt-get install -y wget git libgl1 libglib2.0-0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* &&\
    wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p /opt/conda &&\
    chown -R mluser:mluser /opt/conda

USER mluser
WORKDIR /home/mluser

ENV CONDA_DIR /opt/conda
ENV PATH=$CONDA_DIR/bin:/home/mluser/.local/bin:$PATH

# TODO: Clean up this run
RUN git clone https://github.com/TencentARC/GFPGAN.git gfpgan &&\
    cd gfpgan &&\
    pip install basicsr facexlib realesrgan &&\
    pip install -r requirements.txt &&\
    python setup.py develop &&\
    conda install pytorch torchvision cudatoolkit=11 -c pytorch-nightly

WORKDIR /home/mluser/gfpgan

ENTRYPOINT [ "python", "inference_gfpgan.py", "-i", "../working/input", "-o", "../working/output" ]