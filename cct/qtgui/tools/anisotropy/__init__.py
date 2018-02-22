from .anisotropy import AnisotropyEvaluator

def run():
    from PyQt5 import QtWidgets
    import sys, pkg_resources, gc
    app = QtWidgets.QApplication(sys.argv)

    mw = AnisotropyEvaluator(credo=None)
    mw.setWindowTitle(mw.windowTitle() + ' v{}'.format(pkg_resources.get_distribution('cct').version))
    app.setWindowIcon(mw.windowIcon())
    mw.show()
    result = app.exec_()
    try:
        mw.deleteLater()
    except RuntimeError:
        pass
    del mw
    gc.collect()
    app.deleteLater()
    gc.collect()
    sys.exit(result)
