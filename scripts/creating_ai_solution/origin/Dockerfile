FROM public.ecr.aws/docker/library/python:3.10-slim-bullseye
RUN apt-get update
RUN apt-get install -y apt-utils
RUN apt-get install -y --no-install-recommends \
         build-essential \
         wget \
         ca-certificates \
         git \
         gcc \
    && rm -rf /var/lib/apt/lists/*

# Install required Python packages
# COPY ai_con_demo/requirements.txt /opt/program/requirements.txt
# RUN pip install --no-cache-dir -r /opt/program/requirements.txt

# Specify encoding
ENV LC_ALL=C.UTF-8

# Set some environment variables
ENV PYTHONUNBUFFERED=TRUE
ENV PYTHONDONTWRITEBYTECODE=TRUE
ENV PATH="/opt/program:${PATH}"

# Set up the program in the image
COPY /alo /opt/program

# Create necessary directories
# RUN mkdir -p /opt/ml/input/data/inference /opt/ml/output

WORKDIR /opt/program
CMD ["python", "main.py"]