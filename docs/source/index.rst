.. Welcome to ALO (AI Learning Organizer) documentation master file, created by
   sphinx-quickstart on Mon Jun  3 14:56:51 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to ALO (AI Learning Organizer)'s documentation!
==================================================================

AI Learning Organizer (ALO) is a specialized framework designed to streamline and simplify the development of AI Solutions. By following the ALO guide, assets are developed and connected into a single ML pipeline for training and inference experiments. Once completed, the solution is containerized through a solution registration Jupyter Notebook, making full use of meerkat's rich resources. Once registered as a meerkat solution, multiple users can easily request AI training and deploy to Edge Devices.

.. toctree::
   :maxdepth: 1
   :caption: Contents

   contents/quick_run
   contents/install_alo
   contents/create_ai_solution
   contents/register_ai_solution
   contents/release_note

.. toctree::
   :maxdepth: 4
   :caption: API documentation

   api/alo

.. toctree::
   :maxdepth: 1
   :caption: changelog

   changelog

Key Features
************

The core features of ALO drastically simplify the AI Solution development process and support a wider range of users in leveraging AI technology to solve domain-specific problems. Let's take a closer look at the main features of ALO.

Easy Experiment Environment Setup
*********************************

ALO provides an environment where AI model experiments can be easily set up using YAML files. It allows users to manipulate various conditions and parameters to conduct effective experiments without deep knowledge of AI models. Even users without expert knowledge of AI can participate in the process of creating and optimizing high-quality AI models.

Efficient AI Solution Development
*********************************

ALO helps optimize AI Contents through various experiments and evolve them into AI Solutions specialized for specific problems. This includes tuning AI model parameters and supporting the packaging of necessary Python modules, code, and sample data into Docker images for registration with Mellerikat. It minimizes the need for engineering code required to operate AI Solutions, enabling data scientists to focus on AI modeling development. ALO makes the transition from experimentation to operation efficient, simplifying and accelerating the development process.

Pipeline Automation and Optimization
************************************

ALO reads AI Contents based on YAML files and uses Git to download the assets needed for ML Pipeline construction, automatically setting up the required ML Pipeline for AI modeling. It executes the ML Pipeline automatically using specified data and modeling parameters, validating and integrating the results according to Mellerikat system requirements. ALO supports efficient model optimization by identifying the optimal model parameters through various experiments.


User Scenario
*************
The user scenario related to ALO is as follows:

1. The data scientist installs ALO via Git in their development environment, such as a personal PC, server, or cloud infrastructure.

2. Based on ALO, they develop an AI Solution using AI Contents or without it. An AI Solution is a technical unit that can train and deploy AI models to solve specific problems.

3. After developing the AI Solution, they register it with AI Conductor via ALO. When the AI Solution is registered in AI Conductor, an instance for training is automatically assigned with the minimum size.

4. After registering the AI Solution, they verify through the AI Solution Test process of ALO whether the training is properly conducted in the assigned instance.

5. If the training result is successfully performed and displayed in AI Conductor, the registration of the AI Solution is successfully completed. Once registered, it is possible to request training and deploy for inference in the Edge App through Edge Conductor.
