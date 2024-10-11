FROM public.ecr.aws/docker/library/python:3.10-slim-bullseye
RUN apt-get update
RUN apt-get install -y apt-utils
RUN apt-get install -y --no-install-recommends \
         build-essential \
         wget \
         ca-certificates \
         git \
         gcc \
         docker.io \
         procps \
         jq \
         libgl1-mesa-glx \
         libglib2.0-0 \
         libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

# Specify encoding
ENV LC_ALL=C.UTF-8

# Set some environment variables
ENV PYTHONUNBUFFERED=TRUE
ENV PYTHONDONTWRITEBYTECODE=TRUE

ENV PATH="/framework:${PATH}"

# Set up the program in the image
COPY /.register_source /framework

WORKDIR /framework

# install requirements
RUN pip3 install --no-cache-dir -r /framework/requirements.txt
COPY ./.package_list/installed_packages.txt /framework/
COPY ./.package_list/requirements.txt /framework/
RUN pip3 install --no-cache-dir -r /framework/installed_packages.txt
RUN pip3 install --no-cache-dir -r /framework/requirements.txt

CMD ["python", "main.py"]