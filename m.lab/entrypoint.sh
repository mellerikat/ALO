#!/bin/bash

# Define the working directory for JupyterLab and VSCode
INTERFACE_DIR="/app/solution-generator/engine/alo_engine"
               

# Ensure the interface directory exists
mkdir -p $INTERFACE_DIR

# Start Jupyter Lab in the interface directory
jupyter lab --notebook-dir=$INTERFACE_DIR --ip=0.0.0.0 --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password='' --allow-root &

# Start VSCode Server in the interface directory
code-server $INTERFACE_DIR --bind-addr 0.0.0.0:8080 --auth none --disable-telemetry &

# Start Streamlit
streamlit run /app/solution-generator/main.py --server.port 39002 &

# Wait for all background jobs to complete
wait
