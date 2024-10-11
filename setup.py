from setuptools import find_packages, setup


def get_install_requires():
    # if check platform using sys.platform == "darwin"
    requires = [
        'gitpython>=3.1.43',
        'pyyaml>=6.0.1',
        'pytz>=2021.3',
        'boto3>=1.34.19',
        'botocore>=1.34.19',
        'psutil>=5.9.5',
        'requests>=2.31.0',
        'redis>=5.0.1',
        'docker>=7.0.0',
        'tabulate>=0.9.0',
        'colorama>=0.4.6',
        'pyfiglet>=1.0.2',
        'pydantic>=2.7.4',
        'pydantic-settings>=2.3.3'
    ]

    return requires


setup(
    name='alo2',
    version='2.0',
    description="ALO (AI Learning Organizer)",
    long_description="ALO (AI Learning Organizer)",
    author='LGE',
    author_email='mellerikat@lge.com',
    url='https://mellerikat.com',
    license='LGE License',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    packages=find_packages(exclude=['solution/*', 'test/*']),
    platforms=['Linux', 'FreeBSD', 'Solaris'],
    python_requires='>=3.7',
    install_requires=get_install_requires(),
    entry_points={
        'console_scripts': [
            'alo = alo.alo:main',
        ]
    },
    # package_data={'example': ['*']},
    # include_package_data=True,
)
