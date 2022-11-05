FROM beverts312/mlbase

RUN git clone https://github.com/TencentARC/GFPGAN.git gfpgan

WORKDIR /home/mluser/gfpgan

RUN pip install basicsr facexlib realesrgan &&\
    pip install -r requirements.txt &&\
    python setup.py develop

ENTRYPOINT [ "python", "inference_gfpgan.py", "-i", "../working/input", "-o", "../working/output" ]