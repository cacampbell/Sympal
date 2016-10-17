from setuptools import setup
from os import path

here = path.abspath(path.dirname(__file__))

setup(
    name='Sympal',
    packages=['Sympal'],
    version='0.5',
    description='Basic end user Sympa listserv management with Python requests',
    url='https://github.com/cacampbell/Sympal',
    download_url='https://github.com/cacampbell/Sympal/tarball/0.5',
    author='Chris Campbell',
    author_email='cacampbell@ucdavis.edu',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='sympa listserv requests',
    install_requires=['DateTime', 'lxml', 'requests'],
)
