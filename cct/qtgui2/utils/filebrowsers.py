import enum
from typing import Optional, List, Union

from PyQt5 import QtWidgets


class FileBrowserMode(enum.Enum):
    OpenFile = enum.auto()
    OpenFiles = enum.auto()
    Directory = enum.auto()
    SaveFile = enum.auto()




def browseFile(mode: FileBrowserMode, parent: QtWidgets.QWidget, caption: str,
               initial_path: str = '', filters: str = 'All files (*)',
               defaultsuffix: Optional[str] = None) -> Union[str, List[str], None]:
    fd = QtWidgets.QFileDialog(parent, caption, initial_path, filters)
    try:
        fd.setModal(True)
        if mode == FileBrowserMode.SaveFile:
            fd.setFileMode(QtWidgets.QFileDialog.AnyFile)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
            fd.setDefaultSuffix(defaultsuffix)
        elif mode == FileBrowserMode.Directory:
            fd.setFileMode(QtWidgets.QFileDialog.Directory)
            fd.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        elif mode == FileBrowserMode.OpenFile:
            fd.setFileMode(QtWidgets.QFileDialog.ExistingFile)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        elif mode == FileBrowserMode.OpenFiles:
            fd.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        else:
            raise ValueError(f'Invalid file browser mode: {mode}')
        if fd.exec() != QtWidgets.QFileDialog.Accept:
            return None
        elif mode == FileBrowserMode.OpenFiles:
            return list(fd.selectedFiles())
        else:
            return fd.selectedFiles()[0]
    finally:
        fd.close()
        fd.destroy()
        fd.deleteLater()


def getOpenFile(parent: QtWidgets.QWidget, caption: str, initial_path: str = '',
                filters: str = 'All files (*)') -> Optional[str]:
    return browseFile(FileBrowserMode.OpenFile, parent, caption, initial_path, filters)


def getOpenFiles(parent: QtWidgets.QWidget, caption: str, initial_path: str = '',
                 filters: str = 'All files (*)') -> Optional[List[str]]:
    return browseFile(FileBrowserMode.OpenFiles, parent, caption, initial_path, filters)


def getDirectory(parent: QtWidgets.QWidget, caption: str, initial_path: str = '') -> Optional[str]:
    return browseFile(FileBrowserMode.Directory, parent, caption, initial_path)


def getSaveFile(parent: QtWidgets.QWidget, caption: str, initial_path: str = '', filters: str = 'All files (*)',
                defaultsuffix: Optional[str] = None) -> Optional[str]:
    return browseFile(FileBrowserMode.SaveFile, parent, caption, initial_path, filters, defaultsuffix)


def browseMask(parentwidget: QtWidgets.QWidget) -> Optional[str]:
    return getOpenFile(parentwidget, 'Select a mask file', '', 'Mask files (*.mat *.npy);;All files (*)')
