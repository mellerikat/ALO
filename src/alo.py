import json 
import os
import random
import sys
import shutil
import subprocess
import traceback
from datetime import datetime, timezone
from git import Repo, GitCommandError
import pyfiglet
from time import time 
import yaml
from src.artifacts import Aritifacts
from src.constants import *
from src.external import ExternalHandler 
from src.install import Packages
from src.logger import ProcessLogger  
from src.pipeline import Pipeline
from src.redis import RedisList, RedisPubSub
from src.sagemaker_handler import SagemakerHandler 
from src.solution_register import SolutionRegister
from src.utils import print_color, _log_process, _log_show, refresh_log
from src.yaml import Metadata

class ALO:
    ## copyright and license
    copyright_notice = """
    Copyright (c) 2024, ALO Software
    
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of ALO Software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.
    
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

    Contributor: Sehyun Song, Wonjun Sung, Woosung Jang
    """

    def __init__(self, config = None, system = None, mode = 'all', loop = False, computing = 'local'):
        """ Initialize experimental plan (experimental_plan.yaml), operational plan (solution_metadata), 
            types of pipelines (train, inference), and mode of operation (always-on)

        Args:
            config      (str): experimental_plan.yaml path 
            system      (str): solution_metadata.yaml path or system metadata json string  
            mode        (str): alo pipeline mode (all, train, inference)
            loop        ( - ): infinite loop operation mode if this option exists
            computing   (str): computing resource for pipeline execution (local, sagemaker) 

        Returns: -

        """
        self._make_art(" Let's ALO  -  ! !")
        print_color(self.copyright_notice, 'BOLD')
        ## logger initialize
        self._init_logger()
        ## necessary classes initialize
        self._init_class()
        ## setup alolib
        self._set_alolib()
        exp_plan_path = config
        self.enable_loop = loop
        self.computing_mode = computing
        pipeline_type = mode
        self.system_envs = {}
        ## init redis 
        self._init_redis() 
        if exp_plan_path == "" or exp_plan_path == None:
            exp_plan_path = DEFAULT_EXP_PLAN
        self._get_alo_version()
        ## set_metadata() could be empty or only partial keys exist. Only overwrtie existing keys.
        solution_metadata = self.load_solution_metadata(system)
        ## setup metadata
        self.set_metadata(exp_plan_path, solution_metadata, pipeline_type)
        ## artifacts home initialize 
        self.system_envs['artifacts'] = self.artifact.set_artifacts()
        self.system_envs['train_history'] ={}
        self.system_envs['inference_history'] ={}
        ## set redis 
        self._set_redis(self.system_envs)

    def pipeline(self, experimental_plan={}, pipeline_type = 'train_pipeline', train_id=''):
        """ make pipeline instance

        Args:
            experimental_plan   (dict): loaded experimental plan yaml
            pipeline_type       (str) : pipeline type (train_pipeline, inference_pipeline)
            train_id            (str) : train experimental id
        
        Returns: 
            pipeline            (object) : Pipeline instance

        """
        assert pipeline_type in ['train_pipeline', 'inference_pipeline']
        ## train_id is only supported for inference pipeline 
        if not train_id == '':
            if pipeline_type == 'train_pipeline':
                self.proc_logger.process_error(f"The train_id must be empty. (train_id = {train_id})")
            else:
                self._load_history_model(train_id)
                self.system_envs['inference_history']['train_id'] = train_id
        else:
            ## upload train_id from previous information (data already exists in train_artifacts)
            file = TRAIN_ARTIFACTS_PATH + EXPERIMENTAL_HISTORY_PATH
            if os.path.exists(file):
                with open(file, 'r') as f:
                    history = json.load(f)
                    self.system_envs['inference_history']['train_id'] = history['id']
            else:
                self.system_envs['inference_history']['train_id'] = 'none'
        if experimental_plan in [{}, "", None]: 
            experimental_plan = self.exp_yaml
        ## make pipeline instance
        pipeline = Pipeline(experimental_plan, pipeline_type, self.system_envs)
        return pipeline

    def main(self):
        """ setup and execute pipeline according to mode 
            (modes supported: loop, batch, sagemaker)

        Args: -
        
        Returns: -

        """
        ## (loop operation mode) - pipeline fixed as inference_pipeline / boot_on=True at inital
        if self.enable_loop: 
            ## boot-on process
            try:
                ## inference_pipeline only 
                pipe = self.system_envs['pipeline_list'][0] 
                # set current pipeline into system envs
                self.system_envs['current_pipeline'] = pipe
                _log_process(f"{pipe} in loop")
                ## execute pipline 
                pipeline = self._execute_pipeline(pipe) 
                _log_process(f"Finish boot-on", highlight=True)
                ## cancel boot_on mode after finish booting
                self.system_envs['boot_on'] = False
            except: 
                try: 
                    self.proc_logger.process_error("Failed to boot-on.")
                finally: 
                    self._error_backup(pipe)
            ## infinite loop
            self._publish_redis_msg("alo_status", "waiting")
            while True: 
                try:
                    ## wait redis message from edgeapp
                    sol_meta_str = self._lget_redis_msg("request_inference")['solution_metadata']
                    sol_meta_dict = self.load_solution_metadata(sol_meta_str)    
                    self.set_metadata(sol_meta=sol_meta_dict, pipeline_type=pipe.split('_')[0])
                    ## _empty_artifacts() (@ pipeline.py - pipeline_setup()) does not refresh log directory. Refresh log here.
                    refresh_log(pipe) 
                    pipeline = self._execute_pipeline(pipe)
                    ## update redis runs_state 
                    self.system_envs['runs_status'] = pipeline.system_envs['runs_status']
                except:
                    ## update redis runs_state when error occurs for executing pipeline
                    self.system_envs['runs_status'] = pipeline.system_envs['runs_status']
                    ## return to loop & continue (do not kill main.py process when error occurs in loop mode)
                    _ = self.error_loop(pipe)  
                    ## initialize inference pipeline's metadata
                    self.set_metadata(pipeline_type=pipe.split('_')[0]) 
        ## modes except for loop mode
        else:
            ## (sagemaker mode) boot_on is True at initial
            if self.computing_mode == 'sagemaker':
                try: 
                    ## local boot-on (fetch asset, alolib..) 
                    ## support single / dual pipeline, package_list created at boot-on 
                    for pipe in self.system_envs['pipeline_list']:
                        self.system_envs['current_pipeline'] = pipe
                        _log_process(f"Start boot-on {pipe} for sagemaker")
                        ## boot-on mode pipline execution 
                        pipeline = self._execute_pipeline(pipe)
                        _log_process(f"Finish boot-on {pipe} for sagemaker")
                        ## external load data (since boot-on mode skips loading external data)
                        self.ext_data.external_load_data(pipe, self.external_path, self.external_path_permission)
                    ## sagemaker runs with aws sagemaker cloud resource 
                    self.sagemaker_runs()  
                except: 
                    self.error_batch(pipe) 
            ## (normal batch local mode)
            else: 
                try:
                    for pipe in self.system_envs['pipeline_list']:
                        self.system_envs['current_pipeline'] = pipe
                        _log_process(f"Current pipeline: {pipe}")
                        ## execute pipline  
                        pipeline = self._execute_pipeline(pipe)
                        ## FIXME pipeline.history unused? 
                        # pipeline.history()
                except:
                    self.error_batch(pipe) 
    
    def _execute_pipeline(self, pipe): 
        """ execute pipeline (setup, load, run, save)

        Args:
            pipe    (str): pipeline type (train_pipeline, inference_pipeline)
        
        Returns: 
            pipeline    (object) : Pipeline instance

        """
        pipeline_start_time = time()
        pipeline = self.pipeline(pipeline_type=pipe)
        ## setup 
        self._publish_redis_msg("alo_status", "setup")
        pipeline.setup()
        pipeline_setup_time = time()
        ## load
        self._publish_redis_msg("alo_status", "load")
        pipeline.load()
        pipeline_load_time = time()
        ## run
        self._publish_redis_msg("alo_status", "run")
        pipeline.run()
        pipeline_run_time = time()
        ## save 
        self._publish_redis_msg("alo_status", "save")
        pipeline.save()
        pipeline_save_time = time()
        ## execution time logging
        time_info_list = [f"{pipe} setup time: {round(pipeline_setup_time-pipeline_start_time, 3)}s", \
                    f"{pipe} load time: {round(pipeline_load_time-pipeline_setup_time, 3)}s", \
                    f"{pipe} run time: {round(pipeline_run_time-pipeline_load_time, 3)}s", \
                    f"{pipe} save time: {round(pipeline_save_time-pipeline_run_time, 3)}s", \
                    f"{pipe} total time: {round(pipeline_save_time-pipeline_start_time, 3)}s"]
        for time_info in time_info_list: 
            self.proc_logger.process_message(time_info)
        ## show table summary (parsing SHOW keyword in log files)
        _log_show(pipe)
        return pipeline 
    
    def error_loop(self, pipe):
        """ error handler for loop mode 

        Args:
            pipe    (str): pipeline type (train_pipeline, inference_pipeline)
        
        Returns: 
            "loop"  (str): fixed string 

        """
        ## do not kill main.py process when loop mode is True (only warning)
        self.proc_logger.process_warning(f"==========       Error occurs in loop        ==========") 
        self.proc_logger.process_warning(traceback.format_exc())
        ## (redis) send error status to edgeapp 
        fail_str = json.dumps({'status':'fail', 'message':traceback.format_exc()})
        if self.system_envs['runs_status'] == 'init':
            self.system_envs['redis_list_instance'].rput('inference_summary', fail_str)
            self.system_envs['redis_list_instance'].rput('inference_artifacts', fail_str)
        ## summary success message already sent  
        elif self.system_envs['runs_status'] == 'summary': 
            self.system_envs['redis_list_instance'].rput('inference_artifacts', fail_str)
        ## backup error history & save error artifacts 
        try: 
            self._error_backup(pipe)
        except: 
            ## do not kill main.py process when loop mode is True (only warning)
            self.proc_logger.process_warning("Faild to error backup in loop mode")
        return "loop"
        
    def error_batch(self, pipe): 
        """ error handler for batch mode 

        Args:
            pipe    (str): pipeline type (train_pipeline, inference_pipeline)
        
        Returns: -

        """
        ## backup error history & save error artifact / raise error and kill the main.py process
        try: 
            self.proc_logger.process_error(traceback.format_exc())
        finally:
            self._error_backup(pipe)   
    
    def _error_backup(self, pipe):
        """ backup error history & save error artifacts

        Args:
            pipe    (str): pipeline type (train_pipeline, inference_pipeline)
        
        Returns: -

        """
        try:
            ## generate experimental history id
            sttime = self.system_envs['experimental_start_time']
            exp_name = self.system_envs['experimental_name']
            curr = self.system_envs['current_pipeline'].split('_')[0]
            random_number = '{:08}'.format(random.randint(0, 99999999))
            self.system_envs[f"{curr}_history"]['id'] = f'{sttime}-{random_number}-{exp_name}'
            ## always error backup (directory name ends with "_error") - regardless of control['backup_artifacts'] (True or False)
            self.artifact.backup_history(pipe, self.system_envs, backup_exp_plan=self.exp_yaml, error=True, size=self.control['backup_size'])
            # external save artifacts when error occurs
            # format conversion for external_save_artifacts [{k1:v1}, {k2:v2}, ..] --> {k1:v1, k2:v2, ..}    
            external_path = {list(item.keys())[0]:list(item.values())[0] for item in self.exp_yaml['external_path']}
            external_path_permission = {list(item.keys())[0]:list(item.values())[0] for item in self.exp_yaml['external_path_permission']}
            ext_type, ext_saved_path = self.ext_data.external_save_artifacts(pipe, external_path, external_path_permission, self.control['save_inference_format'])
        except Exception as e: 
            raise NotImplementedError(str(e))
        
    def sagemaker_runs(self): 
        """ execute pipeline as sagemaker mode (build docker and run by sagemaker sdk)

        Args: -
        
        Returns: -

        """
        try:
            try:
                ## load sagemaker_config.yaml - (account_id, role, region, ecr_repository, s3_bucket_uri, train_instance_type)
                sm_config = self.meta.get_yaml(SAGEMAKER_CONFIG) 
                sm_handler = SagemakerHandler(self.external_path_permission['aws_key_profile'], sm_config)
                sm_handler.init()
            except Exception as e:
                self.proc_logger.process_error("Failed to init SagemakerHandler. \n" + str(e)) 
            try: 
                ## modify pipeline configurations in copied experimental_plan.yaml for sagemaker docker 
                sm_handler.setup(self.system_envs['pipeline_list']) 
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to setup SagemakerHandler. \n" + str(e))  
            try:
                sm_handler.build_solution()
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to build Sagemaker solution. \n" + str(e))  
            try:           
                sm_handler.fit_estimator() 
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to Sagemaker estimator fit. \n" + str(e))  
            try: 
                sm_handler.download_latest_model(self.control["save_inference_format"])
            except Exception as e: 
                self.proc_logger.process_error(f"Failed to download sagemaker trained model. \n" + str(e)) 
        except:
            self.proc_logger.process_error("Failed to sagemaker runs.") 
        finally: 
            ## FIXME unnecessary ? (remove env. variable)
            os.unsetenv("AWS_PROFILE")

    def register(self, infra_setup=None, solution_info=None,  train_id = '', inference_id = '', username='', password='', upload=True):
        """ register AI solution

        Args:
            solution_info   (str or dict): solution information (path if string) 
            infra_setup     (str or dict): infra setup config (path if string) 
            train_id        (str): train experimental id
            inference_id    (str): inference experimental id 
            username        (str): login user name 
            password        (str): login user password 
            upload          (bool): whether to register solution 
            
        Returns: 
            register        (object): SolutionRegister instance

        """
        ## Search train_id / read experimental plan
        meta = Metadata()
        exp_plan = meta.read_yaml(exp_plan_file=None)
        def _load_pipeline_expplan(pipeline_type, history_id, meta):
            if not pipeline_type in ['train', 'inference']:
                raise ValueError("pipeline_type must be 'train' or 'inference'.")
            base_path = HISTORY_PATH + f'{pipeline_type}/'
            entries = os.listdir(base_path)
            folders = [entry for entry in entries if os.path.isdir(os.path.join(base_path, entry))]
            if not history_id in folders:
                raise ValueError(f"{pipeline_type}_id is not exist.")
            else:
                path = base_path + history_id + '/experimental_plan.yaml'
                exp_plan = meta.get_yaml(path)
                merged_exp_plan = meta.merged_exp_plan(exp_plan, pipeline_type=pipeline_type)
                return merged_exp_plan
        def _pipe_run(exp_plan, pipeline_type):
            pipeline = self.pipeline(exp_plan, pipeline_type)
            pipeline.setup()
            pipeline.load()
            pipeline.run()
            pipeline.save()
        ## load experimental plan from the id's directory / execute pipeline (since artifact status not ensured)
        if train_id != '':
            train_exp_plan = _load_pipeline_expplan('train', train_id, meta)
            _pipe_run(train_exp_plan, 'train_pipeline')    
        else:
            _pipe_run(exp_plan, 'train_pipeline')    
        if inference_id != '':
            inference_exp_plan = _load_pipeline_expplan('inference', inference_id, meta)
            _pipe_run(inference_exp_plan, 'inference_pipeline')
        else:
            print_color('experimental_plan: \n {}'.format(exp_plan), 'BOLD')
            _pipe_run(exp_plan, 'inference_pipeline')
        ## make experimental plan for solution registration
        if train_id != '':
            if inference_id != '':
                exp_plan_register = inference_exp_plan
            else:
                exp_plan_register = train_exp_plan
        else:
            if inference_id != '':
                exp_plan_register = inference_exp_plan
            else:
                exp_plan_register = exp_plan
        register = SolutionRegister(infra_setup=infra_setup, solution_info=solution_info, experimental_plan=exp_plan_register)
        if upload:
            register.login(username, password)
            register.run(username=username, password=password)
        return register
        
    #####################################
    ####      INTERNAL FUNCTION      #### 
    #####################################
    
    def _make_art(self, msg):
        """ make art print 

        Args:
            msg (str): message tobe art 
            
        Returns: -

        """
        ascii_art = pyfiglet.figlet_format(msg, font="slant")
        print_color("=" * 80 + "\n", 'BOLD-CYAN')
        print_color(ascii_art, 'BOLD-CYAN')
        print_color("\n" + "=" * 80, 'BOLD-CYAN')
    
    def _init_logger(self):
        """ initialize alo master's process logger

        Args: -
            
        Returns: -

        """
        ## remove pre-existing log directory
        train_log_path = TRAIN_LOG_PATH
        inference_log_path = INFERENCE_LOG_PATH
        try: 
            if os.path.exists(train_log_path):
                shutil.rmtree(train_log_path, ignore_errors=True)
            if os.path.exists(inference_log_path):
                shutil.rmtree(inference_log_path, ignore_errors=True)
        except: 
            raise NotImplementedError("Failed to empty log directory.")
        ## process logs into train & inference artifact redundantly
        self.proc_logger = ProcessLogger(PROJECT_HOME)  

    def _init_class(self):
        """ initialize instances needed for alo run 

        Args: -
            
        Returns: -

        """
        _log_process("Start setting-up ALO source code into the memory..")
        self.ext_data = ExternalHandler()
        self.install = Packages()
        self.artifact = Aritifacts()
        self.meta = Metadata()
        _log_process("Finish setting-up ALO source code")

    def _set_alolib(self):
        """ setup alolib (alo library) 
            alolib version must be same as alo's version

        Args: -
            
        Returns: -

        """
        _log_process("Start ALO library installation")
        try:
            alo_main = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            alo_repo = Repo(alo_main)
            alo_ver = alo_repo.active_branch.name
            alolib_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/alolib/"
            sys.path.append(alolib_path)
            if not os.path.exists(PROJECT_HOME + 'alolib'): 
                cloned_repo = Repo.clone_from(ALO_LIB_URI, ALO_LIB, branch=alo_ver)
                self.proc_logger.process_message(f"alolib {alo_ver} git pull success.\n")
            else: 
                self.proc_logger.process_message("alolib already exists in local path.\n")
                alolib_repo = Repo(alolib_path)
                alolib_ver = alolib_repo.active_branch.name
                if alo_ver != alolib_ver: 
                    self.proc_logger.process_message("alolib version mismatch. Try to reinstall \n")
                    shutil.rmtree(ALO_LIB)
                    cloned_repo = Repo.clone_from(ALO_LIB_URI, ALO_LIB, branch=alo_ver)
        except GitCommandError as e:
            self.proc_logger.process_error(e)
        req = os.path.join(alolib_path, "requirements.txt")
        ## subprocess used since pip package's stability is not ensured
        result = subprocess.run(['pip', 'install', '-r', req], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0:
            self.proc_logger.process_message("Success installing alolib requirements.txt")
            self.proc_logger.process_message(result.stdout)
        else:
            self.proc_logger.process_error(f"Failed installing alolib requirements.txt : \n {result.stderr}")
        _log_process("Finish ALO library installation")
        
    def _get_alo_version(self):
        """ get alo's version

        Args: -
            
        Returns: -

        """
        _log_process("Check ALO version")
        with open(PROJECT_HOME + '.git/HEAD', 'r') as f:
            ref = f.readline().strip()
        ## ref format ~ "ref: refs/heads/{branch name}" --> parse only branch
        if ref.startswith('ref:'):
            __version__ = ref.split('/')[-1]
        ## Detached HEAD status (not branch name but commit hash)
        else:
            __version__ = ref  
        self.system_envs['alo_version'] = __version__
        self.proc_logger.process_message(f"ALO version = {self.system_envs['alo_version']}")
        _log_process("Finish ALO version check")

    def set_metadata(self, exp_plan_path = DEFAULT_EXP_PLAN, sol_meta = {}, pipeline_type = 'train_pipeline'):
        """ Read & update experimental plan  
            (The information of solution metadata ins overwritten onto experimental plan) 

        Args:
            exp_plan_path   (str): experimental_plan.yaml path 
            sol_meta        (dict): solution metadata dict 
            pipeline_type   (str): pipeline type (train_pipeline, inference_pipeline)
            
        Returns: -

        """
        ## update system_envs
        self.system_envs['experimental_start_time'] = datetime.now(timezone.utc).strftime(TIME_FORMAT)
        self.system_envs['solution_metadata'] = sol_meta
        self.system_envs['experimental_plan_path'] = exp_plan_path
        ## load experimental_plan.yaml
        _log_process("Load experimental_plan.yaml")
        ## solution metadata overwitten into experimental plan
        self.exp_yaml = self.meta.read_yaml(sol_meta = sol_meta, exp_plan_file = exp_plan_path, system_envs = self.system_envs)
        _log_process("Finish loading experimental_plan.yaml")
        ## FIXME if 'COMPUTING' os environmental variable already in use, it can cause some problems.
        if os.getenv('COMPUTING') == 'sagemaker': 
            ## update experimental plan yaml for sagemaker mode
            self._set_sagemaker()   
        ## set meta attributes into alo class attributes
        self._set_attr()
        ## sagemaker mode 
        if self.computing_mode != 'local': 
            self.system_envs = self._set_system_envs(pipeline_type, True, self.system_envs)
        else:
            ## (loop mode) after boot-on sequence (boot-on off status at system_envs (=False))
            if 'boot_on' in self.system_envs.keys(): 
                self.system_envs = self._set_system_envs(pipeline_type, self.system_envs['boot_on'], self.system_envs)
            ## (loop mode) boot-on = True at initial  
            ## or (normal mode)  
            else:  
                self.system_envs = self._set_system_envs(pipeline_type, self.enable_loop, self.system_envs)
        ## boot-on start message after meta information update completes.
        if self.system_envs['boot_on'] == True: 
            _log_process("Start booting sequence...", highlight=True)

    def _set_system_envs(self, pipeline_type, boot_on, system_envs):
        """ Setup system envs

        Args:
            pipeline_type   (str): pipeline type (train_pipeline, inference_pipeine)
            boot_on         (bool): boot mode (True, False)
            system_envs     (dict): system envs (interface for alo src files) 
            
        Returns: 
            system_envs     (dict): updated system envs

        """
        _log_process("Setup ALO system environments")
        ## solution metadata keys are already updated at yaml.py - _update_yaml()
        ## however, if some keys don't exist, set as None
        solution_metadata_keys = ['solution_metadata_version', 'q_inference_summary', \
                'q_inference_artifacts', 'q_inference_artifacts', 'redis_host', 'redis_port', 'redis_db_number', \
                'inference_result_datatype', 'train_datatype']
        for k in solution_metadata_keys: 
            if k not in system_envs.keys(): 
                system_envs[k] = None
        if 'pipeline_mode' not in system_envs.keys():
            system_envs['pipeline_mode'] = pipeline_type
        ## 'init': initial status / 'summary': success 'q_inference_summary'/ 'artifacts': success 'q_inference_artifacts'
        system_envs['runs_status'] = 'init'         
        system_envs['boot_on'] = boot_on
        system_envs['loop'] = self.enable_loop
        system_envs['start_time'] = datetime.now().strftime("%y%m%d_%H%M%S")
        ## (loop mode)
        if boot_on and self.computing_mode == 'local': 
            system_envs['pipeline_list'] = ['inference_pipeline']
        ## (normal or sagemaker mode)
        else: 
            if pipeline_type == 'all':
                system_envs['pipeline_list'] = [*self.user_parameters]
            else:
                system_envs['pipeline_list'] = [f"{pipeline_type}_pipeline"]
        self.proc_logger.process_message(f"system_envs: {system_envs}")
        _log_process("Finish ALO system environments setup")
        return system_envs

    def load_solution_metadata(self, system_value):
        """ load solution metadata and convert to dict (from json)

        Args:
            system_value (str): main.py --system value (solution_metadata.yaml path or solution metadata json string)

        Returns:
            json_loaded (dict): solution metadata dict from json

        """
        try: 
            ## if solution metadata is ~.yaml (file format), load it 
            _log_process("Start loading solution-metadata")
            if system_value is None:
                json_loaded = {} 
                self.proc_logger.process_message("Solution metadata file name not entered. Skip updating solution metadata into experimental_plan.")
            ## empty dict
            elif len(system_value) == 0: 
                json_loaded = {}
                self.proc_logger.process_message("Empty solution metadata file name entered. Skip updating solution metadata into experimental_plan.")
            else:
                ## load from yaml file   
                if system_value.endswith('.yaml'):
                    try:
                        with open(system_value, encoding='UTF-8') as file:
                            content = yaml.load(file, Loader=yaml.FullLoader)  
                        ## yaml to json string
                        json_loaded = json.loads(json.dumps(content))
                    except FileNotFoundError:
                        self.proc_logger.process_error(f"The file {system_value} does not exist.")
                else:  
                    json_loaded = json.loads(system_value) 
                _log_process("Finish loading solution-metadata")
                self.proc_logger.process_message(f"==========        Loaded solution_metadata: \n{json_loaded}")
        except: 
            if self.redis_pubsub is not None:
                self.redis_pubsub.publish("alo_fail", json.dumps(self.redis_error_table["E111"])) 
        ## dict from json 
        return json_loaded 
    
    def _set_sagemaker(self):
        """ Setup experimental plan for sagemaker mode 

        Args: -
            
        Returns: -

        """
        from sagemaker_training import environment      
        sagemaker_output_path = environment.Environment().model_dir
        for i, v in enumerate(self.exp_yaml['external_path']):
            ## since data is uploaded into sagemaker docker's input directory, do not enter the external data path at experimental plan
            if 'load_train_data_path' in v.keys(): 
                self.exp_yaml['external_path'][i] = {'load_train_data_path': None}
            elif 'load_inference_data_path' in v.keys(): 
                self.exp_yaml['external_path'][i] = {'load_inference_data_path': None}
            ## (NOTE **) whether to external save train, inference each or both is determined in pipeline_list created at set_system_envs 
            ## converts save_train_artifacts_path to sagemaker model save directory
            elif 'save_train_artifacts_path' in v.keys(): 
                self.exp_yaml['external_path'][i] = {'save_train_artifacts_path': sagemaker_output_path}
            ## converts inference_artifacts_path to sagemaker model save directory
            elif 'save_inference_artifacts_path' in v.keys(): 
                self.exp_yaml['external_path'][i] = {'save_inference_artifacts_path': sagemaker_output_path}      
        ## get_asset_source to once (git clone asset may not implements in sagemaker docker)
        for i, v in enumerate(self.exp_yaml['control']):
            if 'get_asset_source' in v.keys(): 
                self.exp_yaml['control'][i] = {'get_asset_source': 'once'}
        ## (NOTE **) save experimental plan yaml since it should be loaded at pipline.py (in sagemaker docker)
        self.meta.save_yaml(self.exp_yaml, DEFAULT_EXP_PLAN)
        
    def _load_history_model(self, train_id):
        """ load model from history by train id

        Args:
            train_id    (str): experimental train id
            
        Returns: -

        """
        ## check whether train_id exists in history
        base_path = HISTORY_PATH + 'train/'
        entries = os.listdir(base_path)
        folders = [entry for entry in entries if os.path.isdir(os.path.join(base_path, entry))]
        if not train_id in folders:
            raise Exception(f"The train_id must be one of {folders}. (train_id={train_id})")
        ## copy model in the history to train_artifacts
        src_path = HISTORY_PATH + 'train/' + train_id + '/models/'
        dst_path = TRAIN_ARTIFACTS_PATH + 'models/'
        # remove estination directory if already exists
        if os.path.exists(dst_path):
            shutil.rmtree(dst_path)
        shutil.copytree(src_path, dst_path)
        self.proc_logger.process_message(f"The model is copied from {src_path} to {dst_path}.")

    def _set_attr(self):
        """ Set meta attributes into alo self variables 

        Args: -
            
        Returns: -

        """
        self.user_parameters = self.meta.user_parameters
        self.asset_source = self.meta.asset_source
        self.external_path = self.meta.external_path
        self.external_path_permission = self.meta.external_path_permission
        self.control = self.meta.control

    def _lget_redis_msg(self, redis_channel):
        """ lget redis list's message 

        Args: 
            redis_key   (str): redis channel name (e.g. "request_inference")
            
        Returns: 
            msg_dict    (dict): message from edgeapp (solution metadata dict)

        """
        # (isBlocking=True) wait until redis msg arrival 
        start_msg = self.redis_list.lget(redis_channel, isBlocking=True)
        if start_msg is not None:
            msg_dict = json.loads(start_msg.decode('utf-8')) 
        return msg_dict

    def _read_redis_error_table(self): 
        """ make redis publish alo_fail dict (json loaded) 
            (channel: alo_fail) 
        
        Args: -
            
        Returns: -

        """
        try: 
            # read error code / name / comment  from file 
            with open(REDIS_ERROR_TABLE, 'r', encoding='utf-8') as file:
                redis_err_table = json.load(file)
            return redis_err_table
        except: 
            self.proc_logger.process_error("Failed to read redis error table")
            
    def _init_redis(self):
        """ initialize redis related instance and set into system_envs

        Args: -

        Returns: -

        """
        self.redis_list = None
        self.redis_pubsub = None 
        self.system_envs['redis_list_instance'] = None
        self.system_envs['redis_pubsub_instance'] = None 

    def _set_redis(self, system_envs: dict):
        """ setup redis list, pubsub objects if in boot & loop mode 

        Args: 
            system_envs   (dict): environmental info. of internal interface

        Returns: -

        """
        ## read redis error table 
        self.redis_error_table = self._read_redis_error_table()
        self.system_envs['redis_error_table'] = self.redis_error_table
        if system_envs['boot_on'] and system_envs['loop']:
            self.redis_list = RedisList(host=system_envs['redis_host'], port=system_envs['redis_port'], db=system_envs['redis_db_number'])
            self.redis_pubsub = RedisPubSub(host=system_envs['redis_host'], port=system_envs['redis_port'], db=system_envs['redis_db_number'])
            self.redis_pubsub.publish("alo_status", "booting")
            ## save in system_envs for transferring to the pipeline.py 
            self.system_envs['redis_list_instance'] = self.redis_list
            self.system_envs['redis_pubsub_instance'] = self.redis_pubsub
        else: 
            pass 
            
    def _publish_redis_msg(self, channel: str, msg: str): 
        """ publish redis message if redis_pubsub object is not None 

        Args: 
            channel (str): redis publish channel 
            msg     (str): message tobe published

        Returns: -

        """
        if self.redis_pubsub is not None: 
            self.redis_pubsub.publish(channel, msg)
        else: 
            pass