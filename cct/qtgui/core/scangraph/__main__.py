import itertools
import sys

import numpy as np
from PyQt5 import QtWidgets

from .scangraph import ScanGraph

scanfile = '/mnt/credo_data/2017/scan/credoscan.spec'
scannr = 10

with open(scanfile, 'rt') as f:
    l = f.readline()
    while not l.startswith('#S {} '.format(scannr)):
        l = f.readline()
        if not l:
            raise RuntimeError('End of file while waiting for start of scan {}'.format(scannr))
        pass
    l = ''
    while not l.startswith('#L '):
        l = f.readline()
    columns = l.split()[1:]
    data = []
    while True:
        try:
            data.append(tuple([float(x) for x in f.readline().split()]))
            if not data[-1]:
                del data[-1]
            else:
                pass
        except ValueError:
            break
    scandatatype = np.dtype(list(zip(columns, itertools.repeat('f'))))
    scandata = np.array(data, dtype=scandatatype)

a = QtWidgets.QApplication(sys.argv)
w = ScanGraph()
w.setCurve(scandata)
w.show()
sys.exit(a.exec_())
