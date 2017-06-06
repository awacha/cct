import sys

from PyQt5.QtWidgets import QApplication

from .capillarymeasurement import CapillaryMeasurement

app = QApplication(sys.argv)
cm = CapillaryMeasurement()
cm.show()
sys.exit(app.exec_())
