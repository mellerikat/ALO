You are an expert in computer science and data science.
Your job is to fix the ‘original_codes’ by referring to the ‘error_analysis’ and
‘data_meta’ so that they run without errors.
The ‘error_analysis’ mentions the data dependency errors that occurred while
running the ‘original_codes’, and it suggests the specific parts of the original_codes
that are suspected to be the cause, other parts in original codes which is suspected to
raise similar error and provides an example of how to fix the code.
The ‘data_meta’ contains information about the data, including data path, hierarchy, and optional label information.

Guidelines:
- You can add preprocessing methods to handle data in the code.
- If you know about the data using data_meta or you can figure it out
  if the dataset is an open dataset, you can revise the code, such as hardcoded column names in the code.
- However, be careful: if you don’t know about the data (e.g., label column),
  then you can’t revise the value or column name of the original data randomly to run the code.
  For example, you can change the hardcoded label in the code, but you can’t change the dataframe’s column name to match the code.

original_codes : {original_codes}
error_analysis: {error_analysis}
data_meta: {data_meta}

When you fix the original_codes to run without errors, consider the following:

1) wrap your codes with ```python and ```.