Quick Run
========================

This page quickly guides you through the process of installing the latest version of ALO and installing the sample AI Solution (Titanic) to register an AI Solution without modifying the code. If you can run Linux commands and have an environment with Jupyter notebook installed, you can proceed with the following steps. (Note: Some commands may differ if Jupyter notebook is running inside a docker container.)


.. contents:: Topics

step1: Start ALO
***********************
For more details, please refer to the installation page (Install ALO).

step1-1: Install ALO
--------------------
Write the desired working folder name in {project_name}.



step1-2: Set up ALO runtime environment
---------------------------------------
Below is an example of setting up an Anaconda virtual environment, but you can set up any virtual environment that can run Python 3.10, such as pyenv.

.. code-block:: console

    conda init bash ## Initialize conda environment
    exec bash  ## Restart bash
    # conda create --prefix /home/jovyan/testenv python=3.10   ## Method to install a non-deletable virtual environment when running jupyter in docker
    conda create -n {virtual_env_name} python=3.10 ## 3.10 is required

    conda activate {virtual_env_name}  ## If conda activate does not work, run exec bash
    pip install -r requirements.txt

    # [Additional work for running the solution registration Jupyter Notebook]
    pip install ipykernel
    # If the virtual environment name is /home/jovyan/testenv, write only testenv.
    python -m ipykernel install --user --name {virtual_env_name} --display-name {jupyter-virtual-env-display-name}


Note : For setting up a virtual environment using pyenv + pipenv, please refer to the Install ALO - Development Environment Setup page.

step2: Develop Solution
***********************
If you need to understand the AI Solutions running in ALO, you can check the sample solution 'titanic' by installing it.


step2-1: Install and run Titanic
--------------------------------
.. code-block:: console

    # Install the solution folder in the {project_home} location where ALO main.py exists
    git clone https://github.com/mellerikat/titanic.git solution
    python main.py  # Run ALO

step2-2: Install and run AI Contents
------------------------------------
AI Contents refers to reusable AI Solutions designed to solve various industry challenges using AI. These can be applied to tasks by simply changing data in the YAML file settings without additional development. For more details, refer to the AI Contents page (AI Contents).

Note: For Git code access to AI Contents, refer to (AI Contents Access).

.. list-table::
   :header-rows: 1

   * - AI Contents
     - Description
   * - TCR
     - | TCR is AI Contents for classification/regression on tabular data, automatically performing preprocessing, sampling, HPO, and optimal model selection.
       | https://github.com/mellerikat-aicontents/Tabular-Classification-Regression.git
   * - GCR
     - | GCR has the same input/output as TCR, but uses Graph ML technology to extract and utilize hidden information from the data, improving model accuracy and handling data with missing values.
       | https://github.com/mellerikat-aicontents/Graph-powered-Classification-Regression.git
   * - FCST
     - | FCST is AI Contents that analyzes time series data and predicts future values.
       | http://mod.lge.com/hub/dxadvtech/aicontents/biz_forecasting.git
   * - CV
     - | CV is AI Contents for automating the classification of various types of classes through image classification models.
       | https://github.com/mellerikat-aicontents/Vision-Classification.git
   * - PAD
     - | PAD stands for Point Anomaly Detection and is AI Contents for detecting whether point-type time series data is normal or abnormal.
       | https://github.com/mellerikat-aicontents/Anomaly-Detection.git
   * - MAD
     - | MAD is AI Contents used for early sensing of anomalies or defects by monitoring multiple variables simultaneously and detecting anomalies.
       | http://mod.lge.com/hub/dxadvtech/aicontents/mad.git

Running AI Contents is the same as running the Titanic sample solution. Just refer to the Git addresses in the table above and change them accordingly.

.. code-block:: console

    # Login Caching
    git config --global credential.helper 'cache --timeout=864000'

    # Install the solution folder in the {project_home} location where ALO main.py exists
    git clone {AI Contents git address} solution
    python main.py  # Run ALO

step3: Register Solution
************************
To register an AI Solution, follow the procedures in the register-ai-solution.ipynb guide.

1. Set up Infra for solution registration
2. Write AI Solution information
3. Execute solution registration
4. Conduct AI training test

step3-1: Set up Infra
---------------------
| Write the environment information for registering the AI Solution in ./{project_home}/setting/infra_setup.yaml.
| For more details, refer to the Infra setup page (Configure Infra).

.. code-block:: console

    "VERSION": 1.0  ## solution_metadata version
    "AIC_URI": "https://web.aic-dev.lgebigdata.com/"
    "REGION": "ap-northeast-2"
    "WORKSPACE_NAME": "cism-ws"
    "BUILD_METHOD": "docker"  ## docker, buildah
    "LOGIN_MODE": "static" ## ldap, static
    "AWS_KEY_FILE: "aws.key"
    "REPOSITORY_TAGS": [ ],
    "SUPPORT_TRAINING" : True, #True, False
    ## aws codebuild (cloud build)
    "REMOTE_BUILD": False
    ## 'type': 'WINDOWS_CONTAINER'|'LINUX_CONTAINER'|'LINUX_GPU_CONTAINER'|'ARM_CONTAINER'|'WINDOWS_SERVER_2019_CONTAINER'|'LINUX_LAMBDA_CONTAINER'|'ARM_LAMBDA_CONTAINER',
    "CODEBUILD_ENV_TYPE": "LINUX_CONTAINER"
    ## 'computeType': 'BUILD_GENERAL1_SMALL'|'BUILD_GENERAL1_MEDIUM'|'BUILD_GENERAL1_LARGE'|'BUILD_GENERAL1_XLARGE'|'BUILD_GENERAL1_2XLARGE'|'BUILD_LAMBDA_1GB'|'BUILD_LAMBDA_2GB'|'BUILD_LAMBDA_4GB'|'BUILD_LAMBDA_8GB'|'BUILD_LAMBDA_10GB',
    "CODEBUILD_ENV_COMPUTE_TYPE": "BUILD_GENERAL1_SMALL"

step3-2: Write AI Solution information
--------------------------------------
Run the login cell in the register-ai-solution.ipynb Jupyter Notebook using the assigned account, then fill in and execute the following cell content. The key field is 'solution_name', and the name of the AI Solution to be registered should be entered in lowercase letters and hyphens. For more details, refer to the AI Solution registration page (Register AI Solution).


.. code-block:: python

    #----------------------------------------#
    #        Write AI Solution Spec          #
    #----------------------------------------#
    solution_info = {
        'solution_name': 'my-ai-solution-name',
        'inference_only': False, # True, False
        'solution_update': False, # True, False

        'solution_type': 'private',
        'contents_type': {
                'support_labeling': False, # True, False
                'inference_result_datatype': 'table', # 'image'
                'train_datatype': 'table', # 'image'
                'labeling_column_name': 'my_label', # The column name of the data to be labeled in Edge Conductor
        },
        'train_gpu': False, # True, False
        'inference_gpu': False, # True, False
        "inference_arm": False # True, False
    }


step3-3: Execute AI Solution registration
-----------------------------------------
Execute the following steps in register-ai-solution.ipynb.

.. code-block:: python

    import sys
    from solution_register import SolutionRegister

    try:
        del sys.modules['solution_register']
    except:
        pass

    register = SolutionRegister(infra_setup=infra_setup, solution_info=solution_info)
    register.run(username=username, password=password)

step3-4: Conduct training test
------------------------------

If the AI Solution registration is successful, test whether the training runs correctly in AI Conductor. Running the code below will automatically create an AI Solution Instance and Stream, check for training success, and then delete the Stream, concluding the test.

.. code-block:: python

    register.run_train(
        status_period = 10,  ## Set the interval (in seconds) for checking the training status
        delete_solution = False,  ## Set whether to delete the solution
    )