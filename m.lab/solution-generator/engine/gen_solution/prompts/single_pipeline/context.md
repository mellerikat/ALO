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

1. The experimental_plan.yaml template must adhere to the JSON dumped format when creating experimental_plan.yaml. If there are additional Python modules required to execute the original code, add them under the <requirements> section.
2. When creating experimental_plan.yaml, include the model-related parameters that users can change from the original code under the <arguments> section. The default values for these arguments should match those specified in the original code.
3. Add the model-related parameters as arguments to the <inference> function in the pipeline.py code and assign them as variables instead of fixed values in the code lines so that changes in experimental_plan.yaml will be reflected in pipeline.py.
4. Ensure the pipeline.py template format is maintained when converting the original code, including the <data_path> for data required for training and inference, and the <output_path> for saving inference results. If the inference result is a dataframe, save it as output.csv in the output_path. If it is an image, save it as output.jpg in the <output_path>. The output file must be only one image file, only one csv file, or only one of each. For example, the <output_path> should have files corresponding to the following three cases:
    Case 1: output.csv
    Case 2: output.png (or jpg, svg, etc.)
    Case 3: output.csv, output.png (or jpg, svg, etc.)
5. For <summary> in the inference function, insert a string representing the inference result into the <result> variable. Convert values denoting inference performance, such as accuracy, to a basic Python float type between 0.0 and 1.0 and place them in the <score> variable. Populate the <note> variable with a description of the inference results.
6. Remove any visualization-related code lines in the original code that might halt code execution, such as show(). However, you must not remove any other lines from the original code.