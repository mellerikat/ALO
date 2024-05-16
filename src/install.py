import pkg_resources
import os
import subprocess
import sys
from collections import defaultdict
from src.logger import ProcessLogger 
from src.constants import *

#--------------------------------------------------------------------------------------------------------------------------
#    GLOBAL VARIABLE
#--------------------------------------------------------------------------------------------------------------------------
PROC_LOGGER = ProcessLogger(PROJECT_HOME)
#--------------------------------------------------------------------------------------------------------------------------

class Packages:
    def extract_requirements_txt(self, step_name): 
        """ If a requirements.txt exists within the ALO master or each user asset, 
            extract the packages written inside it into a list.

        Args:           
            step_name   (str): Name of the asset to be installed under assets directory.
            
        Returns:
            packages_in_txt (list): package list in requirements.txt

        """
        fixed_txt_name  = 'requirements.txt'
        packages_in_txt = []
        if fixed_txt_name in os.listdir(ASSET_HOME + step_name):
            with open(ASSET_HOME + step_name + '/' + fixed_txt_name, 'r') as req_txt:  
                for pkg in req_txt: 
                    ## Remove the newline character at the end of the line (=package)
                    pkg = pkg.strip() 
                    packages_in_txt.append(pkg)
            return packages_in_txt
        else: 
            PROC_LOGGER.process_error(f"<< {fixed_txt_name} >> dose not exist in << assets/{step_name} folder >>. \n \
                However, you have written {fixed_txt_name} at that step in << config/experimental_plan.yaml >>. \n \
                Please remove {fixed_txt_name} in the yaml file.")

    def _install_packages(self, dup_checked_requirements_dict, dup_chk_set): 
        """ install all the packages 

        Args:           
            step_name   (str): Name of the asset to be installed under assets directory.
            
        Returns:
            packages_in_txt (list): package list in requirements.txt

        """
        fixed_txt_name  = 'requirements.txt'
        total_num_install = len(dup_chk_set)
        count = 1
        ## Check for the existence of each package in the {priority_sorted_pkg_list} \
        ## in the user environment and install if not present.
        for step_name, package_list in dup_checked_requirements_dict.items(): 
            PROC_LOGGER.process_message(f"======================================== Start dependency installation : << {step_name} >> ")
            for package in package_list:
                PROC_LOGGER.process_message(f"Start checking existence & installing package - {package} | Progress: ( {count} / {total_num_install} total packages ) ")
                count += 1
                if "--force-reinstall" in package: 
                    try: 
                        PROC_LOGGER.process_message(f'>>> Start installing package - {package}')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package.replace('--force-reinstall', '').strip(), '--force-reinstall'])            
                    except OSError as e:
                        PROC_LOGGER.process_error(f"Error occurs while --force-reinstalling {package} ~ " + e)  
                    continue 
                ## Check whether the same version is already installed.
                try:
                    ## {package} @ git+http://~.git@ver~ format in the requirements.txt don't cause conflict.
                    ## Even if the user specifies the package name without a version, the following code will pass
                    pkg_resources.get_distribution(package) 
                    PROC_LOGGER.process_message(f'[OK] << {package} >> already exists')
                ## In the case where the package is not installed at all in the user's virtual environment.
                except pkg_resources.DistributionNotFound:  
                    try: 
                        PROC_LOGGER.process_message(f'>>> Start installing package - {package}')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                    except OSError as e:
                        ## only support txt file named requirements.txt
                        PROC_LOGGER.process_error(f"Error occurs while installing {package}. If you want to install from packages written file, make sure that your file name is << {fixed_txt_name} >> ~ " + e)
                ## Reinstall if installed but the version is different.
                except pkg_resources.VersionConflict:  
                    try:
                        PROC_LOGGER.process_warning(f'VersionConflict occurs. Start re-installing package << {package} >>. \n You should check the dependency for the package among assets.')
                        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                    except OSError as e:
                        PROC_LOGGER.process_error(f"Error occurs while re-installing {package} ~ " + e)  
                except pkg_resources.ResolutionError:  
                    PROC_LOGGER.process_error(f'ResolutionError occurs while installing package {package} @ {step_name} step. \n Please check the package name or dependency with other asset.')
                except pkg_resources.ExtractionError: 
                    PROC_LOGGER.process_error(f'ExtractionError occurs while installing package {package} @ {step_name} step. \n Please check the package name or dependency with other asset.')
        PROC_LOGGER.process_message(f"======================================== Finish dependency installation \n")
        return 

    def check_install_requirements(self, requirements_dict):
        """ Check whether the packages required for each step (written in requirements.txt or experimental_plan.yaml) 
            are installed in the current user's virtual environment; if not, attempt to install them.
            Packages with the --force-reinstall argument are reinstalled separately at the end, even if they are duplicates.
        
        Args:           
            requirements_dict   (dict): requirements needed for each step.
                                        (key - step name, value - requirements list)
            
        Returns: -

        """ 
        fixed_txt_name = 'requirements.txt'
        ## If a requirements.txt exists for a certain step, check for the existence of the txt file within \
        ## the assets/{asset} directory and extract the packages listed within it.
        extracted_requirements_dict = dict() 
        for step_name, requirements_list in requirements_dict.items(): 
            if requirements_list==None or requirements_list ==[]: 
                continue 
            ## requirements.txt exists
            if fixed_txt_name in requirements_list:
                requirements_txt_list = self.extract_requirements_txt(step_name)
                requirements_txt_list = sorted(set(requirements_txt_list), key = lambda x: requirements_txt_list.index(x)) 
                yaml_written_list = sorted(set(requirements_list), key = lambda x: requirements_list.index(x)) 
                fixed_txt_index = yaml_written_list.index(fixed_txt_name)                
                extracted_requirements_dict[step_name] = yaml_written_list[ : fixed_txt_index] + requirements_txt_list + yaml_written_list[fixed_txt_index + 1 : ]
            ## requirements.txt does not exist
            else:
                extracted_requirements_dict[step_name] = sorted(set(requirements_list), key = lambda x: requirements_list.index(x)) 
        ## (install priority)
        ## 1. ALO master dependency packages \
        ## 2. earlier steps in the current pipeline \ 
        ## 3. within the same step, packages written directly in the yaml take precedence over requirements.txt
        dup_checked_requirements_dict = defaultdict(list) 
        dup_chk_set = set() 
        force_reinstall_list = [] 
        for step_name, requirements_list in extracted_requirements_dict.items(): 
            for pkg in requirements_list: 
                pkg_name = pkg.replace(" ", "") 
                ## after removing all spaces, extract the base name of the package, \
                ## excluding comparison operators and version numbers. 
                if "--force-reinstall" in pkg_name: 
                    ## not {pkg_name} but {pkg} since --force-reinstall needs a space in front
                    force_reinstall_list.append(pkg)
                    dup_chk_set.add(pkg)
                    continue 
                ## extract the base name of the package, excluding the version and any comments
                base_pkg_name = "" 
                ## skip lines that contain comments or are empty in the requirements.txt file
                if pkg_name.startswith("#") or pkg_name == "":
                    continue 
                ## FIXME should an error be raised if there are any other special characters present?  
                ## not support other than comparison operators
                ## case <, <=
                if '<' in pkg_name:  
                    base_pkg_name = pkg_name[ : pkg_name.index('<')]
                ## case >, >=
                elif '>' in pkg_name:   
                    base_pkg_name = pkg_name[ : pkg_name.index('>')]
                ## case == 
                elif ('=' in pkg_name) and ('<' not in pkg_name) and ('>' not in pkg_name): 
                    base_pkg_name = pkg_name[ : pkg_name.index('=')]
                ## case version not specified
                else:
                    base_pkg_name = pkg_name  
                ## Remove comments placed beside, rather than above the package name
                if '#' in base_pkg_name: 
                    base_pkg_name = base_pkg_name[ : base_pkg_name.index('#')]
                if '#' in pkg_name: 
                    pkg_name = pkg_name[ : pkg_name.index('#')]      
                ## gathering the dependency packages of ALO main and all assets, \
                ## if there are duplicate packages with different versions, \
                ## install only the dependencies of the step (=asset) that is executed first
                if base_pkg_name in dup_chk_set: 
                    PROC_LOGGER.process_message(f'>>> Ignored installing << {pkg_name} >>. Another version would be installed in the previous step.')
                else: 
                    dup_chk_set.add(base_pkg_name)
                    dup_checked_requirements_dict[step_name].append(pkg_name)
        ## force reinstall is added to perform the installation again at the end
        dup_checked_requirements_dict['force-reinstall'] = force_reinstall_list
        ## install packages 
        self._install_packages(dup_checked_requirements_dict, dup_chk_set)
        return dup_checked_requirements_dict, extracted_requirements_dict
