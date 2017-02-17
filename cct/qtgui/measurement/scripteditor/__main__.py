import sys

from PyQt5 import QtWidgets

from .scripteditor import ScriptEditor

a = QtWidgets.QApplication(sys.argv)
w = ScriptEditor()
w.show()
sys.exit(a.exec_())
