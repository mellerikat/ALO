The following templates should be maintained when creating pipeline.py and experimental_plan.yaml.
--- 
### pipeline.py template 
 {pipeline_template} 
--- 
--- 
### experimental_plan.yaml template 
 {experimental_plan_template}
--- 

Here are rules to follow when converting the original code:

1. The experimental_plan.yaml template must adhere to the JSON dumped format when creating experimental_plan.yaml. Under the <requirements> section, the package list should be written with the version specified. Do not delete the original version unless there is an error.
2. When creating experimental_plan.yaml, include the model-related parameters that users can change from the original code under the <arguments> section. For parameters related to training, list them under the arguments section in the <alo_train> section. For parameters related to inference, list them under the arguments section in the <alo_inference> section. The default values for these arguments should match those specified in the original code. Finally, if you extract the necessary arguments from the original code and reflect them similarly to the <alo_sample_arg> of the templates, be sure to delete <alo_sample_arg> from experimental_plan.yaml and pipeline.py.
3. Add the train-related parameters as arguments to the <alo_train> function in the pipeline.py code and assign them as variables instead of fixed values in the code lines so that changes in experimental_plan.yaml will be reflected in pipeline.py.
4. Add the inference-related parameters as arguments to the <alo_inference> function in the pipeline.py code and assign them as variables instead of fixed values in the code lines so that changes in experimental_plan.yaml will be reflected in pipeline.py.
5. Ensure the pipeline.py template format is maintained when converting the original code, including the <train_data_path> and <inference_data_path> for data required for training and inference, <model_path> for saving trained model and loading for the model and the <output_path> for saving inference results. Save the trained model to <model_path> within the <alo_train> function, and load the model from <model_path> within the <alo_inference> function when performing inference. 
6. If the inference result is a dataframe, save it as output.csv in the <output_path>. If it is an image, save it as output.jpg in the <output_path>. The output file must be only one image file, only one csv file, or only one of each. For example, the <output_path> should have files corresponding to the following three cases:
    Case 1: output.csv
    Case 2: output.png (or jpg, svg, etc.)
    Case 3: output.csv, output.png (or jpg, svg, etc.)
6. For <summary> in the inference function, insert a string representing the inference result into the <result> variable. Convert values denoting inference performance, such as accuracy, to a basic Python float type between 0.0 and 1.0 and place them in the <score> variable. Populate the <note> variable with a description of the inference results.
7. Remove any visualization-related code lines in the original code that might halt code execution, such as show(), etc. However, you must not remove any other lines from the original code.