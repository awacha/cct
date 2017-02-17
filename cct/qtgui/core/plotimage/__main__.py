import sys

import sastool
import scipy.io
from PyQt5 import QtWidgets

from .plotimage import PlotImage

header = sastool.io.credo_cct.Header.new_from_file('/mnt/credo_data/2016/eval2d/crd_00003.pickle.gz')
mask = scipy.io.loadmat('/mnt/credo_data/2016/mask/Shortest/mask_shortest_20160113.mat')['mask_shortest_20160113']
exposure = sastool.io.credo_cct.Exposure.new_from_file('/mnt/credo_data/2016/eval2d/crd_00003.npz', header, mask)
app = QtWidgets.QApplication(sys.argv)
w = PlotImage()
w.setExposure(exposure)
w.show()
sys.exit(app.exec_())
