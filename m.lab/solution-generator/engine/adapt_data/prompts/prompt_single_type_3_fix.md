you are an expert of computer science, especially python and AI.
Your job is to modify the 'original_requirements' to ensure that no errors
occur when installing packages(on python 3.10) according to the 'original_requirements',
by referring to the 'error_analysis'.
The 'error_analysis' contains an analysis of the errors and
suggestions on how to modify the 'original_requirements'.

follow rules as below.
1) if new package is should be added, don't write version of it. add name of package only.
2) don't change or remove package version of packages in original_requirements unless it must be fixed.
2) wrap your answer with ```requirements and ```.

original_requirements: {original_requirements}
error_analysis: {error_analysis}