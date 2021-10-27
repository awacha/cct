from typing import Any, List, Optional

from PyQt5 import QtCore


class Stack(QtCore.QObject):
    """A LIFO: last in, first out storage, aka a stack.

    It is browsable: a pointer marks its current location.

    Only the most recently put element can be removed, however.
    """
    pointerChanged = QtCore.pyqtSignal(int)
    stackChanged = QtCore.pyqtSignal()
    _stack: List[Any]
    _pointer: int = -1

    def __init__(self, parent: QtCore.QObject):
        super().__init__(parent)
        self._stack = []
        self._pointer = -1

    def reset(self):
        """Empty the stack"""
        self._stack = []
        self._pointer = -1
        self.pointerChanged.emit(self._pointer)
        self.stackChanged.emit()

    def isEmpty(self) -> bool:
        """Check if the stack is empty"""
        return not self._stack

    def truncate(self):
        """Truncate the stack: remove all entries after the pointer."""
        if self.isEmpty():
            return
        self._stack = self._stack[:self._pointer + 1]
        self.stackChanged.emit()

    def back(self) -> int:
        """Move the pointer back in the stack (toward older elements)"""
        return self.goto(self._pointer - 1)

    def forward(self) -> int:
        """Move the pointer forward in the stack (toward newer elements)"""
        return self.goto(self._pointer + 1)

    def push(self, data: Any) -> int:
        """Add a new entry to the current position. The stack is truncated beforehand, i.e. all elements newer than
        the current one are discarded."""
        self.truncate()
        self._stack.append(data)
        self._pointer = len(self._stack) - 1
        self.stackChanged.emit()
        self.pointerChanged.emit(self._pointer)
        return self._pointer

    def pop(self) -> Any:
        """Get (and remove) the most recent element of the stack."""
        data = self._stack[-1]
        self._stack = self._stack[:-1]
        if self._pointer >= len(self._stack):
            self._pointer = len(self._stack) -1
            self.pointerChanged.emit(self._pointer)
        self.stackChanged.emit()
        return data

    def goto(self, index: int):
        """Move the pointer to the specified element"""
        if index < 0 or index >=len(self._stack):
            # invaid index: do not move.
            raise IndexError('Invalid stack index')
        self._pointer = index
        self.pointerChanged.emit(self._pointer)
        return self._pointer

    def canGoBack(self) -> bool:
        return self._pointer > 0

    def canGoForward(self) -> bool:
        return self._pointer < len(self._stack) - 1

    def __len__(self) -> int:
        return len(self._stack)

    def where(self) -> int:
        return self._pointer

    def get(self) -> Any:
        """Peek at the index at the pointer (without removing it)"""
        return self._stack[self._pointer]
