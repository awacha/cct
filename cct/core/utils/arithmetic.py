import copy


class ArithmeticBase(object):
    """A mixin class for defining simple arithmetics with minimal user effort.

    Usage: subclass this object and define ALL of the following methods:
        __imul__(self, value): in-place multiplication of 'self' by 'value'
        __iadd__(self, value): in-place addition of 'value' to 'self'
        __neg__(self): negation, i.e. '-self': should return an instance of the
            same class
        _recip(self): reciprocal, i.e. '1.0/self'. Should return an instance of
            the same class
        copy(self): should return a deep copy of the current object.

        Note, that __imul__ and __iadd__ too should return the modified version
            of 'self'!

    Methods __add__, __radd__, __sub__, __isub__, __rsub__, __mul__, __rmul__,
        __div__, __rdiv__ and __idiv__ are constructed automatically from the
        given functions (assuming commutative addition and multiplication)
    """

    def __add__(self, value):
        obj = copy.deepcopy(self)
        obj = obj.__iadd__(value)
        return obj

    def __radd__(self, value):
        retval = self + value
        if retval is NotImplemented:
            raise NotImplementedError(
                'addition is not implemented between %s and %s types' % (type(self), type(value)))
        return retval

    def __isub__(self, value):
        return self.__iadd__(-value)

    def __sub__(self, value):
        obj = copy.deepcopy(self)
        obj = obj.__isub__(value)
        return obj

    def __rsub__(self, value):
        retval = (-self) + value
        if retval is NotImplemented:
            raise NotImplementedError(
                'subtraction is not implemented between %s and %s types' % (type(self), type(value)))
        return retval

    def __mul__(self, value):
        obj = copy.deepcopy(self)
        obj = obj.__imul__(value)
        return obj

    def __rmul__(self, value):
        retval = self * value
        if retval is NotImplemented:
            raise NotImplementedError(
                'multiplication is not implemented between %s and %s types' % (type(self), type(value)))
        return retval

    def __itruediv__(self, value):
        try:
            value_recip = value._recip()
        except AttributeError:
            value_recip = 1.0 / value
        return self.__imul__(value_recip)

    def __truediv__(self, value):
        obj = copy.deepcopy(self)
        return obj.__itruediv__(value)

    def __rtruediv__(self, value):
        retval = self._recip() * value
        if retval is NotImplemented:
            raise NotImplementedError(
                'division is not implemented between %s and %s types' % (type(self), type(value)))
        return retval

    def __iadd__(self, value):
        raise NotImplementedError

    def __imul__(self, value):
        raise NotImplementedError

    def __neg__(self):
        raise NotImplementedError

    def _recip(self):
        raise NotImplementedError
