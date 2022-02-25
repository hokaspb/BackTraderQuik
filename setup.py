#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2022 Igor Chechet
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import os.path
import codecs  # To use a consistent encoding
import setuptools

here = os.path.abspath(os.path.dirname(__file__))
with codecs.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

pname = 'BackTraderQuik'
vname = '1.0'

#with open(os.path.join(pname, vname)) as f:
#with codecs.open(os.path.join(here, 'QuikPY/QuikPY.py'), encoding='utf-8') as f:
#    exec(compile(f.read(), vname, 'exec'))

gurl = 'https://github.com/cia76/' + pname

setuptools.setup(
    name=pname,
    version=vname,
    description='Quik samles for BackTrader',
    long_description=long_description,
    url=gurl,
#    download_url=gdurl,
    author='Igor Chechet',
#    author_email='chechet@gmail.com',
    license='GPLv3+',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',
        'Topic :: Software Development',
        'Topic :: Office/Business :: Financial',
        ('License :: OSI Approved :: ' +
         'GNU General Public License v3 or later (GPLv3+)'),
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Operating System :: OS Independent',
    ],
    keywords=['trading', 'development'],
    packages=['BackTraderQuik'],
)
