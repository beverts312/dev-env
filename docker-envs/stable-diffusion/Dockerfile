FROM beverts312/mlbase

RUN git clone https://github.com/basujindal/stable-diffusion.git

WORKDIR /home/mluser/stable-diffusion

RUN eval "$($CONDA_DIR/bin/conda shell.bash hook)" && \
    conda env create -f environment.yaml && \
    conda activate ldm && \
    pip install gradio==3.1.7

ENV PYTHONUNBUFFERED=1
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860
EXPOSE 7860

COPY ./bootstrap.sh /home/mluser/stable-diffusion/bootstrap.sh

RUN ln -s /home/mluser/data /home/mluser/stable-diffusion/models/ldm/stable-diffusion-v1

ENTRYPOINT ["/home/mluser/stable-diffusion/bootstrap.sh"]

CMD python optimizedSD/txt2img_gradio.py