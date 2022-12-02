import enum
import logging
from typing import Optional, List, Union

from PySide6 import QtWidgets

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
            fd.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
            fd.setDefaultSuffix(defaultsuffix)
        elif mode == FileBrowserMode.Directory:
            fd.setFileMode(QtWidgets.QFileDialog.FileMode.Directory)
            fd.setOption(QtWidgets.QFileDialog.Option.ShowDirsOnly, True)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptOpen)
        elif mode == FileBrowserMode.OpenFile:
            fd.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptOpen)
        elif mode == FileBrowserMode.OpenFiles:
            fd.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFiles)
            fd.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptOpen)
        else:
            raise ValueError(f'Invalid file browser mode: {mode}')
        if (result := fd.exec()) != QtWidgets.QFileDialog.DialogCode.Accepted:
            logger.debug(f'File dialog return value: {result}')
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
