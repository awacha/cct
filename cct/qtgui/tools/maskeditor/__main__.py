import pickle
import sys

from PyQt5 import QtWidgets

from .maskeditor import MaskEditor

# header = sastool.io.credo_saxsctrl.Header.new_from_file('/mnt/credo_data/2015/eval2d/crd_0/crd_01019.pickle.gz')
# mask = scipy.io.loadmat('/mnt/credo_data/2015/mask/Short/mask_short_20150112.mat')['mask_short_20150112']
# exposure = sastool.io.credo_saxsctrl.Exposure.new_from_file('/mnt/credo_processing/2015/External/HUNSAS_15_01_Trypsin_Lipo/20150113/crd_0/crd_00003.npz', header, mask)
with open('/mnt/credo_processing/2015/Inhouse/Inhouse_15_01_DPPC_UA/201501/DPPC_UA_Chol_DSPE-PEG_2_50C.pickle',
          'rb') as f:
    exposure = pickle.load(f)
app = QtWidgets.QApplication(sys.argv)
w = MaskEditor()
w.setExposure(exposure)
w.show()
sys.exit(app.exec_())
