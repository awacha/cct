#!/usb/bin/env python
import os

from Cython.Build import cythonize
from numpy import get_include
from setuptools import setup, find_packages
from setuptools.extension import Extension


def getresourcefiles():
    print('Generating resource list', flush=True)
    reslist = []
    for directory, subdirs, files in os.walk('cct/resource'):
        reslist.extend([os.path.join(directory, f).split('/', 1)[1] for f in files])
    print('Generated resource list:\n  ' + '\n  '.join(x for x in reslist) + '\n', flush=True)
    return reslist


def update_languagespec():
    from cct.core.commands import Command
    allcommands = sorted([c.name for c in Command.allcommands()])
    with open('cct/resource/language-specs/cct.lang.in', 'rt', encoding='utf-8') as fin:
        with open('cct/resource/language-specs/cct.lang', 'wt', encoding='utf-8') as fout:
            for l in fin:
                if l.startswith('% KEYWORDS %'):
                    for c in allcommands:
                        fout.write('      <keyword>%s</keyword>\n' % c)
                else:
                    fout.write(l)
    print('Updated language spec. Command list:\n' + ', '.join(allcommands))


extensions = [Extension("cct.gui.tools.optimizegeometry.estimateworksize",
                        ["cct/gui/tools/optimizegeometry/estimateworksize.pyx"], include_dirs=[get_include()])]


update_languagespec()
setup(name='cct', version='2.0.2', author='Andras Wacha',
      author_email='awacha@gmail.com', url='http://github.com/awacha/cct',
      description='CREDO Control Tool',
      packages=find_packages(),
      #      cmdclass = {'build_ext': build_ext},
      ext_modules=cythonize(extensions),
      install_requires=['numpy>=1.11.1', 'scipy>=0.18.0', 'matplotlib>=1.5.2', 'sastool>=0.7.2', 'pymodbustcp>=0.0.13',
                        'pykerberos>=1.1.10', 'psutil>=4.1.0', 'cairocffi>=0.7.2'],
      entry_points={'gui_scripts': ['cct = cct.gui.__main__:run'],
                    },
      keywords="saxs sans sas small-angle scattering x-ray instrument control",
      license="",
      package_data={'': getresourcefiles()},
      #      include_package_data=True,
      zip_safe=False,
      )
