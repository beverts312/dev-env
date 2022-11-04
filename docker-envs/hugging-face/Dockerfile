FROM beverts312/mlbase

RUN mkdir -p /home/mluser/hface

WORKDIR /home/mluser/hface

RUN pip install \
        torch \
        torchvision \
        torchaudio \
        transformers \
        --extra-index-url https://download.pytorch.org/whl/cu113

RUN pip install timm

COPY ./scripts .
