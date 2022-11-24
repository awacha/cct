from PySide6 import QtGui

def getIconFromTheme(*iconnames) -> QtGui.QIcon:
    for name in iconnames:
        if QtGui.QIcon.hasThemeIcon(name):
            return QtGui.QIcon.fromTheme(name)
    return QtGui.QIcon(iconnames[0])  # rely on the fallback mechanism