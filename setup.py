#!/usb/bin/env python
import os

import numpy as np
from Cython.Build import cythonize
from setuptools import setup, find_packages
from setuptools.extension import Extension


def getresourcefiles():
    print('Generating resource list',flush=True)
    reslist=[]
    for directory, subdirs, files in os.walk('cct/resource'):
        reslist.extend([os.path.join(directory,f).split('/',1)[1] for f in files])
    print('Generated resource list:\n  '+'\n  '.join(x for x in reslist)+'\n',flush=True)
    return reslist

def update_languagespec():
    from cct.core.commands import Command
    allcommands=sorted([c.name for c in Command.allcommands()])
    with open('cct/resource/language-specs/cct.lang.in','rt', encoding='utf-8') as fin:
        with open('cct/resource/language-specs/cct.lang', 'wt', encoding='utf-8') as fout:
            for l in fin:
                if l.startswith('% KEYWORDS %'):
                    for c in allcommands:
                        fout.write('      <keyword>%s</keyword>\n'%c)
                else:
                    fout.write(l)
    print('Updated language spec. Command list:\n'+', '.join(allcommands))


extensions = [Extension("cct.core.utils.radint", ["cct/core/utils/radint.pyx"], include_dirs=[np.get_include()])]

  
update_languagespec()
setup(name='cct', version='1.2.2', author='Andras Wacha',
      author_email='awacha@gmail.com', url='http://github.com/awacha/cct',
      description='CREDO Control Tool',
      packages=find_packages(),
      #      cmdclass = {'build_ext': build_ext},
      ext_modules=cythonize(extensions),
      install_requires=['numpy>=1.0.0', 'scipy>=0.7.0', 'matplotlib', 'sastool', 'pymodbustcp'],
      entry_points={'gui_scripts':['cct = cct.gui.mainwindow:run'],
                    },
      keywords="saxs sans sas small-angle scattering x-ray instrument control",
      license="",
      package_data={'': getresourcefiles()},
      #      include_package_data=True,
      zip_safe=False,
      )
