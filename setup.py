#!/usb/bin/env python
import os
import sys

import codegenerator
from Cython.Build import cythonize
from numpy import get_include
from setuptools import setup, find_packages, Extension

try:
    from PyQt5.uic import compileUi
except ImportError:
    def compileUi(*args):
        pass

codegenerator.writeCode()
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

extensions = [Extension("cct.qtgui.tools.optimizegeometry.estimateworksize",
                        [os.path.join("cct", "qtgui", "tools", "optimizegeometry", "estimateworksize.pyx")],
                        include_dirs=[get_include()]),
              Extension("cct.core.services.accounting.krb5_check_pass",
                        [os.path.join("cct", "core", "services", "accounting", "krb5_check_pass.pyx")],
                        include_dirs=[get_include()], libraries=krb5_libs),
              Extension("cct.core.processing.correlmatrix",
                        [os.path.join("cct", "core", "processing", "correlmatrix.pyx")],
                        include_dirs=[get_include()]),
              ]

print(get_include())
# extensions=[]

# update_languagespec()
setup(name='cct', author='Andras Wacha',
      author_email='awacha@gmail.com', url='http://github.com/awacha/cct',
      description='CREDO Control Tool',
      packages=find_packages(),
      use_scm_version=True,
      setup_requires=['setuptools_scm'],
      #      cmdclass = {'build_ext': build_ext},
      ext_modules=cythonize(extensions),
      install_requires=['appdirs>=1.4.0',
                        'numpy>=1.15.0',
                        'scipy>=1.0.0',
                        'matplotlib>=3.0.0',
                        'sastool>=1.2.3',
                        'pymodbustcp>=0.0.13',
                        'psutil>=4.1.0',
                        'h5py',
                        'pillow',
                        'openpyxl',
                        'sqlalchemy',
                        'adjusttext',
                        'imageio'],
      entry_points={'gui_scripts': ['cct = cct.qtgui.__main__:run',
                                    'cpt = cct.processing.__main__:run',
                                    'cpt2 = cct.processinggui.__main__:run',
                                    'cctmask = cct.qtgui.tools.maskeditor2:run',
                                    'cctanisotropy = cct.qtgui.tools.anisotropy:run',
                                    'cctupdatedb = cct.dbutils.updatedb:run',
                                    'cctsequencebrowser = cct.processing.sequenceinspector.sequencelist:run'],

                    },
      keywords="saxs sans sas small-angle scattering x-ray instrument control",
      license="",
      package_data={'': getresourcefiles()},
      #      include_package_data=True,
      zip_safe=False,
      )
