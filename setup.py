from setuptools import setup
from setuptools import find_packages
from os import path

here = path.abspath(path.dirname(__file__))

setup(
    name='Sympal',
    version='1.0.0',
    description='Sympa list server management API for end users',
    url='https://github.com/cacampbell/Sympal',
    author='Chris Campbell',
    author_email='cacampbell@ucdavis.edu',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='sympa listserv requests',
    py_modules=['Sympal'],
    install_requires=['DateTime', 'lxml', 'requests'],
)
