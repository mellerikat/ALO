# Base image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install necessary OS packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    lsb-release \
    build-essential \
    nodejs \
    npm \
    r-base \
    git \
    && rm -rf /var/lib/apt/lists/*

# # Install pyenv dependencies
# RUN apt-get update && apt-get install -y \
#     make \
#     build-essential \
#     libssl-dev \
#     zlib1g-dev \
#     libbz2-dev \
#     libreadline-dev \
#     libsqlite3-dev \
#     wget \
#     curl \
#     llvm \
#     libncurses5-dev \
#     libncursesw5-dev \
#     xz-utils \
#     tk-dev \
#     libffi-dev \
#     liblzma-dev \
#     python3-openssl \
#     git \
#     && rm -rf /var/lib/apt/lists/*

# # Install pyenv
# ENV PYENV_ROOT="/root/.pyenv"
# ENV PATH="$PYENV_ROOT/bin:$PATH"
# RUN curl https://pyenv.run | bash

# # Set up pyenv in the shell
# ENV PATH="$PYENV_ROOT/shims:$PATH"

# # Install Python 3.10 using pyenv and set it as the global version
# RUN pyenv install 3.10.0 \
#     && pyenv global 3.10.0

# Check the Python version to ensure it's correctly installed
RUN python --version

# Upgrade npm to the latest version
RUN npm install -g npm

# Install JupyterLab and extensions
RUN pip install --no-cache-dir --upgrade pip \
    && pip install jupyterlab jupyter-server-proxy \
    && pip install jupyterlab_code_formatter streamlit

# Install VSCode Server
RUN curl -fsSL https://code-server.dev/install.sh | sh

# Pre-install Python extension for VSCode
RUN code-server --install-extension ms-python.python

# Create VSCode settings folder and settings.json file
RUN mkdir -p /app/.vscode \
    && echo '{ \
        "python.pythonPath": "/app/solution-generator/interface/py310_venv/bin/python" \
    }' > /app/.vscode/settings.json

# Copy jupyter_server_proxy config file
COPY jupyter_server_proxy_config.json /usr/local/share/jupyter/labextensions/@jupyterlab/server-proxy/config.json

# Copy VSCode icon file (optional)
RUN mkdir -p /usr/local/share/jupyter/labextensions/@jupyterlab/server-proxy/static
ADD https://upload.wikimedia.org/wikipedia/commons/9/9a/Visual_Studio_Code_1.35_icon.svg /usr/local/share/jupyter/labextensions/@jupyterlab/server-proxy/static/vscode.svg

# Copy the solution-generator directory
COPY solution-generator /app/solution-generator

# Install Python dependencies from requirements.txt within solution-generator
RUN pip install --no-cache-dir -r /app/solution-generator/requirements.txt

# Install Python dependencies from requirements.txt within solution-generator/engine/alo_engine
RUN pip install --no-cache-dir -r /app/solution-generator/engine/alo_engine/requirements.txt

# Copy kaggle.json to the specified directory
RUN mkdir -p /root/.config/kaggle
COPY kaggle.json /root/.config/kaggle/kaggle.json

# Set the appropriate permissions for kaggle.json
RUN chmod 600 /root/.config/kaggle/kaggle.json

# Expose the ports for JupyterLab, VSCode server, and Streamlit
EXPOSE 8888 8080 39002

# Copy entrypoint script and set script execution environment
COPY entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh

# Set the entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
