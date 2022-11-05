FROM beverts312/mlbase

RUN git clone  https://github.com/gwang-kim/DiffusionCLIP.git diffusion-clip    

WORKDIR /home/mluser/diffusion-clip

RUN pip install -r requirements.txt && \
    pip install git+https://github.com/openai/CLIP.git && \
    pip install scipy

ENTRYPOINT [ "python", "main.py", "--edit_one_image", "--t_0", "500", "--n_inv_step", "40", "--n_test_step", "40", "--n_iter", "1", "--exp", "../working/runs/" ]