FROM beverts312/mlbase

# TODO: Clean up this run
RUN git clone https://github.com/TencentARC/GFPGAN.git gfpgan &&\
    cd gfpgan &&\
    pip install basicsr facexlib realesrgan &&\
    pip install -r requirements.txt &&\
    python setup.py develop &&\
    conda install pytorch torchvision cudatoolkit=11 -c pytorch-nightly

WORKDIR /home/mluser/gfpgan

ENTRYPOINT [ "python", "inference_gfpgan.py", "-i", "../working/input", "-o", "../working/output" ]