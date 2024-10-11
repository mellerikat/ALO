import os
import sys
sys.path.insert(0, os.path.abspath('../..'))
sys.argv = []


# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'ALO(AI Learning Organizer)'
copyright = '2024, AI Advisor. LGE'
author = 'ALO'
release = '3.0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.todo',
    'sphinx.ext.ifconfig',
    # 'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx_rtd_theme'
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

language = "en"
locale_dirs = ['locale/']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

html_favicon = ''
html_logo = ''

host_domain = os.environ.get("host_domain", "")
languages = [lang.strip() for lang in os.environ.get("languages", "en").split(',')]

print(languages)

html_context = {
    'current_language': languages[0],
    'current_version': 'latest',
    'languages': [[lang, f'{host_domain}{("/" + lang) if i > 0 else ""}'] for i, lang in enumerate(languages)]
}
