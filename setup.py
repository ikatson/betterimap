#!/usr/bin/env python

import os.path
from setuptools import setup, find_packages


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(name='betterimap',
      version='0.0.1',
      description='IMAP',
      author='Igor Katson',
      author_email='igor.katson@gmail.com',
      url='https://github.com/ikatson/betterimap',
      packages='betterimap',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Operating System :: POSIX',
          'Programming Language :: Python',
          'Topic :: Software Development :: Libraries :: Python Modules',
      ])
