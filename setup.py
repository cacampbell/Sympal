from setuptools import setup
from os import path

here = path.abspath(path.dirname(__file__))

setup(
    name='Sympal',
    version='0.2',
    description='Sympa list server management API for end users',
    url='https://github.com/cacampbell/Sympal',
    download_url='https://github.com/cacampbell/Sympal/tarball/0.1',
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
    py_modules=['Sympal'],
    install_requires=['DateTime', 'lxml', 'requests'],
)
