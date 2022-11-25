#!/usb/bin/env python
import os
import subprocess
import sys
import re

from numpy import get_include
from setuptools import setup, Extension, Command
from setuptools.command.build_py import build_py
from setuptools.command.develop import develop


class RCCComand(Command):
    """Custom setuptools command to invoke the PyQt resource compiler"""

    description = 'Invoke the PyQt resource compiler'
    user_options = []

    def initialize_options(self) -> None:
        return None

    def finalize_options(self) -> None:
        return None

    def run(self) -> None:
        subprocess.check_call(
            ['pyside6-rcc',
             os.path.join('cct', 'resource', 'icons', 'icons.qrc'),
             '-o', os.path.join('cct', 'resource', 'icons_rc.py'), '-g', 'python']
        )


class BuildUICommand(Command):
    """Custom setuptools command to compile .ui files to _ui.py files"""

    description = 'Compile Qt .ui files to Python modules'
    user_options = []

    def initialize_options(self) -> None:
        return None

    def finalize_options(self) -> None:
        return None

    def run(self):
        """Run the command."""
        self.announce('Compiling Qt .ui files to Python modules', 2)
        for dirpath, dirnames, filenames in os.walk('.'):
            for fn in [fn_ for fn_ in filenames if fn_.endswith('.ui')]:
                fname = os.path.join(dirpath, fn)
                pyfilename = os.path.splitext(fname)[0] + '_ui.py'
                subprocess.check_call(
                    ['pyside6-uic', fname, '-o', pyfilename, '-c', 'pmf', '-g', 'python']
                )
                # adjust import module path for rc
                rcrootpath = os.path.join('cct', 'resource')
                uifiledata = []
                with open(pyfilename, 'rt') as f:
                    for line in f:
                        if m := re.match('^import (?P<rcmodulename>\\w+_rc)$', line):
                            resourcefile = m['rcmodulename']+'.py'
                            if not os.path.exists(os.path.join(rcrootpath, resourcefile)):
                                raise FileNotFoundError(f'Resource file {resourcefile} does not exist in rc root {rcrootpath}.')
                            relpath = os.path.relpath(rcrootpath, dirpath)
                            relmodulepath = '.' + ''.join([x if x != '..' else '.' for x in relpath.split(os.path.sep)])
                            uifiledata.append(f'from {relmodulepath} import {m["rcmodulename"]}\n')
                        else:
                            uifiledata.append(line)
                with open(pyfilename, 'wt') as f:
                    for line in uifiledata:
                        f.write(line)
                self.announce('Compiled UI file: {} -> {}.'.format(fname, pyfilename), 2)


class BuildPyCommand(build_py):
    """Override the default build_py command to require Qt UI and resource compilation"""

    def run(self):
        self.run_command('rcc')
        self.run_command('uic')
        super().run()


class DevelopCommand(develop):
    """Override the default develop command to require Qt UI and resourec compilation"""
    def run(self) -> None:
        self.run_command('rcc')
        self.run_command('uic')
        super().run()


# collect extensions

if sys.platform.lower().startswith('win') and sys.maxsize > 2 ** 32:
    krb5_libs = ['krb5_64']
else:
    krb5_libs = ['krb5']

extensions = []
for dirpath, dirnames, filenames in os.walk('cct'):
    for fn in filenames:
        if not os.path.splitext(fn)[-1] == '.pyx':
            continue
        pyxfilename = os.path.join(dirpath, fn)
        extensions.append(Extension(os.path.splitext(pyxfilename)[0].replace(os.path.sep, '.'),
                                    [pyxfilename],
                                    include_dirs=[get_include()],
                                    libraries=krb5_libs,
                                    # define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]
                                    ))

setup(ext_modules=extensions,
      cmdclass={'build_py': BuildPyCommand,
                'uic': BuildUICommand,
                'rcc': RCCComand,
                'develop': DevelopCommand,
                }
      )
