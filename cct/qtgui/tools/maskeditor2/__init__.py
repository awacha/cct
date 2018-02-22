from .maskeditor import MaskEditor

def run():
    from PyQt5 import QtWidgets
    import sys, pkg_resources, gc
    app = QtWidgets.QApplication(sys.argv)

    mw = MaskEditor(credo=None)
    mw.setWindowTitle(mw.windowTitle() + ' v{}'.format(pkg_resources.get_distribution('cct').version))
    app.setWindowIcon(mw.windowIcon())
    mw.show()
    result = app.exec_()
    mw.deleteLater()
    del mw
    gc.collect()
    app.deleteLater()
    gc.collect()
    sys.exit(result)
