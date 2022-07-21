#!/usb/bin/env python
import os
import subprocess
import sys

from PyQt5.uic import compileUi
from numpy import get_include
from setuptools import setup, Extension, Command
from setuptools.command.build_py import build_py


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
            ['pyrcc5',
             os.path.join('cct', 'resource', 'icons', 'icons.qrc'),
             '-o', os.path.join('cct', 'resource', 'icons_rc.py')]
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
                with open(pyfilename, 'wt', encoding='utf-8') as pyfile:
                    compileUi(fname, pyfile, from_imports=True, import_from='cct.resource')
                self.announce('Compiled UI file: {} -> {}.'.format(fname, pyfilename), 2)


class BuildPyCommand(build_py):
    """Override the default build_py command to require Qt UI and resource compilation"""

    def run(self):
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
                'rcc': RCCComand, }
      )
