from typing import Any
from PyQt5 import QtCore

class Stack(QtCore.QObject):
    pointerChanged = QtCore.pyqtSignal(int)
    stackChanged = QtCore.pyqtSignal()

    def __init__(self, parent:QtCore.QObject):
        super().__init__(parent)
        self.reset()

    def reset(self):
        self._stack = []
        self._pointer = -1
        self.pointerChanged.emit(self._pointer)
        self.stackChanged.emit()

    def truncate(self):
        if self._pointer<0:
            return
        self._stack = self._stack[:self._pointer+1]
        self.stackChanged.emit()
        self.pointerChanged.emit(self._pointer)

    def back(self) -> int:
        return self.goto(self._pointer-1)

    def forward(self) -> int:
        return self.goto(self._pointer+1)

    def push(self, data:Any) -> int:
        if len(self._stack) == 0:
            self._stack=[data]
        else:
            self._stack=self._stack[:self._pointer+1]
            self._stack.append(data)
        self._pointer=len(self._stack)-1
        self.stackChanged.emit()
        self.pointerChanged.emit(self._pointer)
        return self._pointer

    def pop(self) -> Any:
        data = self._stack[-1]
        self._stack=self._stack[:-1]
        if self._pointer <0 or self._pointer> len(self._stack)-1:
            self._pointer = len(self._stack)-1
            self.pointerChanged.emit(self._pointer)
        return data

    def goto(self, index:int):
        if index >=0 and index<=len(self._stack)-1:
            self._pointer = index
            self.pointerChanged.emit(self._pointer)
        return self._pointer

    def canGoBack(self) -> bool:
        return self._pointer>0

    def canGoForward(self) -> bool:
        return self._pointer<len(self._stack)-1

    def __len__(self) -> int:
        return len(self._stack)

    def where(self) -> int:
        return self._pointer

    def get(self) -> Any:
        return self._stack[self._pointer]
