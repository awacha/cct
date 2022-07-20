#!/usb/bin/env python
import os
import sys

from Cython.Build import cythonize
from numpy import get_include
from setuptools import setup, find_packages, Extension

try:
    from PyQt5.uic import compileUi
except ImportError:
    def compileUi(*args):
        pass

rcc_output = os.path.join('cct', 'resource', 'icons_rc.py')
rcc_input = os.path.join('cct', 'resource', 'icons', 'icons.qrc')
os.system('pyrcc5 {} -o {}'.format(rcc_input, rcc_output))


def compile_uis(packageroot):
    if compileUi is None:
        return
    for dirpath, dirnames, filenames in os.walk(packageroot):
        for fn in [fn_ for fn_ in filenames if fn_.endswith('.ui')]:
            fname = os.path.join(dirpath, fn)
            pyfilename = os.path.splitext(fname)[0] + '_ui.py'
            with open(pyfilename, 'wt', encoding='utf-8') as pyfile:
                compileUi(fname, pyfile, from_imports=True, import_from='cct.resource')
            print('Compiled UI file: {} -> {}.'.format(fname, pyfilename))


compile_uis(os.path.join('cct'))


def getresourcefiles():
    print('Generating resource list', flush=True)
    reslist = []
    for directory, subdirs, files in os.walk(os.path.join('cct', 'resource')):
        reslist.extend([os.path.join(directory, f).split(os.path.sep, 1)[1] for f in files])
    print('Generated resource list:\n  ' + '\n  '.join(x for x in reslist) + '\n', flush=True)
    return reslist


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
#                                    define_macros=[("NPY_NO_DEPRECATED_API", "NPY_1_7_API_VERSION")]
                                    ))

setup(ext_modules=cythonize(extensions),
      )
