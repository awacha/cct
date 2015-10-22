#!/usb/bin/env python
#print('Importing setuptools',flush=True)
from setuptools import setup, find_packages
#print('Importing setuptools.extension',flush=True)
from setuptools.extension import Extension
#print('Importing setuptools',flush=True)
#from distutils.sysconfig import get_python_lib, get_python_inc
#print('Importing os',flush=True)
import os

#with open('.version_last','rt') as f:
#    version_last=int(f.read())

def getresourcefiles():
    print('Generating resource list',flush=True)
    reslist=[]
    for directory, subdirs, files in os.walk('cct/resource'):
        reslist.extend([os.path.join(directory,f).split('/',1)[1] for f in files])
    print('Generated resource list:\n  '+'\n  '.join(x for x in reslist)+'\n',flush=True)
    return reslist
    
  
#print('Finding packages',flush=True)
#packages=['cct.'+x for x in find_packages('cct')]
#print('Found packages:',packages,flush=True)
#print('Finding resources',flush=True)
#resources=getresourcefiles()
#print('Running setup()',flush=True)
setup(name='cct', version='0.0.1', author='Andras Wacha',
      author_email='awacha@gmail.com', url='http://github.com/awacha/cct',
      description='CREDO Control Tool',
      packages=find_packages(),
      # cmdclass = {'build_ext': build_ext},
      #ext_modules=cythonize(ext_modules),
      install_requires=['numpy>=1.0.0', 'scipy>=0.7.0', 'matplotlib', 'sastool', 'sasgui', 'pymodbustcp'],
      entry_points={'gui_scripts':['cct = cct.gui.mainwindow:run'],
                    },
      keywords="saxs sans sas small-angle scattering x-ray instrument control",
      license="",
      package_data={'': getresourcefiles()},
#      include_package_data=True,
      zip_safe=False,
)
