import matplotlib.scale
import matplotlib.ticker
import matplotlib.transforms
import numpy as np


class GuinierQScale(matplotlib.scale.ScaleBase):
    name = 'guinierq'

    def __init__(self, axis, **kwargs):
        super().__init__(axis, **kwargs)

    def get_transform(self):
        return self.SquareTransform()

    def limit_range_for_scale(self, vmin, vmax, minpos):
        print('vmin: {}, vmax: {}, minpos: {}'.format(vmin,vmax,minpos))
        if not np.isfinite(minpos): minpos = 1e-300
        retval = (minpos if vmin <=0 else vmin, minpos if vmax<=0 else vmax)
        print('Returning ({}, {})'.format(*retval))
        return retval

    def set_default_locators_and_formatters(self, axis):
        axis.set_major_locator(matplotlib.ticker.LogLocator())
        axis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
        axis.set_minor_locator(matplotlib.ticker.NullLocator())
        axis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    class SquareTransform(matplotlib.transforms.Transform):
        input_dims = 1
        output_dims = 1
        is_separable = True

        def transform_non_affine(self, values):
            return values**2

        def inverted(self):
            return GuinierQScale.SquareRootTransform()

    class SquareRootTransform(matplotlib.transforms.Transform):
        input_dims = 1
        output_dims = 1
        is_separable = True

        def transform_non_affine(self, values):
            return values**0.5

        def inverted(self):
            return GuinierQScale.SquareTransform()

matplotlib.scale.register_scale(GuinierQScale)
