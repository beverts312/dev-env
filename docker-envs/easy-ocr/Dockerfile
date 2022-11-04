FROM beverts312/mlbase

RUN pip install \
        easyocr \
        torch \
        torchvision \
        torchaudio \
        --extra-index-url https://download.pytorch.org/whl/cu113


RUN pip install easyocr

COPY entrypoint.py entrypoint.py

ENTRYPOINT ["python", "entrypoint.py"]