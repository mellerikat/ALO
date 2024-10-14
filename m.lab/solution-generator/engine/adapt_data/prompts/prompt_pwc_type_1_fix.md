you are an expert of computer science, especially python and AI.
Your job is fix the 'original_codes' by refering to the 'error_analysis' and
so that they run without errors. The 'original_codes' is the implementation
of the algorithm described in the paper_summary. The 'error_analysis' mentions
the possible causes of the errors that occurred while running the 'original_codes',
and the specific parts of the original_codes that are suspected to be the cause
and an example of how to fix the code.
algorithm : {algorithm}

original_codes : {original_codes}
error_analysis: {error_analysis}

When you fix the original_codes to run without errors, consider the following:

1)The paper_summary may introduce several algorithms.
Ignore all except the one we need to implement.
2) The paper_summary is a summary of the paper that describes the
algorithm we need to implement without errors.
3) The code_summary contains descriptions of methods related to the
algorithm we need to implement, which we can import and use directly without
having to implement them ourselves.
4) The generation_guide is a kind of code skeleton that describes in sentences
the overall code structure that the algorithm we need to implement should have
5) wrap your codes with ```python and ```.

And follow rules as below when you fix 'original_codes'.there's no fault in rules.
rules: {rules}

paper_summary : {paper_summary}
code_summary : {code_summary}
generation_guide : {generation_guide}