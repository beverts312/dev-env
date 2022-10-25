FROM beverts312/mlbase

RUN pip install \
        imageio-ffmpeg==0.4.2 \
        backgroundremover \
        torch \
        torchvision \
        torchaudio \
        --extra-index-url https://download.pytorch.org/whl/cu113

COPY ./entrypoint.sh ./entrypoint.sh

ENTRYPOINT ["/bin/bash", "./entrypoint.sh"]