from setuptools import setup, find_packages

def readme():
    with open('README.md') as f:
        README = f.read()
    return README
exec(open('specc/version.py').read())
setup(
    name="spec-client",
    version=__version__,
    description="Module for communicating with Spec control software from Jupyter at the SGM Beamline at the Canadian Light Source.",
    long_description=readme(),
    long_description_content_type="text/markdown",
    url="https://github.lightsource.ca/arthurz/JupyterSpecClient",
    author="Zachary Arthur",
    author_email="zachary.arthur@lightsource.ca",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7"
    ],
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "requests",
        "numpy"
    ]


)