
--- 
### original code
 {original_code} 
--- 
Request 1: Split the original code into training and inference sections, and create them as the <alo_train> function and <alo_inference> function in pipeline.py, respectively. If there are lines of code from the original that are needed in both the <alo_train> and <alo_inference> functions, include those lines in both functions. Please wrap the created code with ```python and ```. 

Request 2: Create the contents of experimental_plan.yaml, which is the configuration for the ALO framework's operation structure, in a JSON-dumped format and wrap it with ```json and ```. For the <name>, use a name that accurately reflects the characteristics of the original code, consisting only of lowercase letters and underscores.

For reference, the subdirectory structures under the <train_data_path> and <inference_data_path> are as follows. 
Refer to it when generating the code for reading the data.
--- 
# <train_data_path> 
 {train_input_dir_structure} 
--- 
---
# <inference_data_path>
 {inference_input_dir_structure}
---


