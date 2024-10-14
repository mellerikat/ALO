Codes below is written in Python 3.10.4.
```python
{content}
```
Please provide a list of packages that need to be installed for this Python version in the requirements.txt file format. Exclude the version numbers.

I will save your answer in a variable called response. I intend to save it in requirements.txt using the following code. Do not include any other responses including 'plaintext' or 'python' in your response.
Make sure not to recommend python itself or python built-in libraries (e.g., gc, os, glob, re, warnings) or local file imports (e.g., mb, csv) that cannot be installed with pip install.
Please write the library names in their latest version format, e.g., sklearn should be written as scikit-learn.
```python
with open('requirements.txt', 'w') as file:
    file.write(response.strip())
```
 