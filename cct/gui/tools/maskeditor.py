import os

import numpy as np
from gi.repository import Gtk
from scipy.io import loadmat, savemat

from ..core.exposureloader import ExposureLoader
from ..core.plotimage import PlotImageWidget
from ..core.toolwindow import ToolWindow


class MaskEditor(ToolWindow):
    def _init_gui(self, *args):
        self._el = ExposureLoader(self._instrument)
        self._builder.get_object('loadexposure_expander').add(self._el)
        self._el.connect('open', self.on_loadexposure)
        self._plot2d = PlotImageWidget()
        self._builder.get_object('plotbox').pack_start(self._plot2d._widget, True, True, 0)
        self._mask = None
        self._builder.get_object('toolbar').set_sensitive(False)

    def on_loadexposure(self, exposureloader, im):
        if self._mask is None:
            self._mask = im._mask
        self._im = im
        self._plot2d.set_image(im.val)
        self._plot2d.set_mask(self._mask)
        self._builder.get_object('toolbar').set_sensitive(True)

    def on_new(self, button):
        self._mask = np.ones_like(self._mask)
        self._plot2d.set_mask(self._mask)

    def on_open(self, button):
        if not hasattr(self, '_filechooser'):
            self._filechooser = Gtk.FileChooserDialog('Open mask file...',
                                                      self._window,
                                                      Gtk.FileChooserAction.OPEN,
                                                      ['Open', 1, 'Cancel', 0])
            self._filechooser.set_do_overwrite_confirmation(True)
            self._filefilter = Gtk.FileFilter()
            self._filefilter.add_pattern('*.mat')
            self._filefilter.set_name('Mask files')
            self._filechooser.add_filter(self._filefilter)
        self._filechooser.set_action(Gtk.FileChooserAction.OPEN)
        self._filechooser.get_widget_for_response(1).set_label('Open')
        if self._filechooser.run():
            self._filename = self._filechooser.get_filename()
            mask = loadmat(self._filename)
            self._mask = mask[[k for k in mask.keys() if not k.startswith('__')][0]]
            self._plot2d.set_mask(self._mask)
        self._filechooser.hide()

    def on_save(self, button):
        if not hasattr(self, '_filename'):
            return self.on_saveas(button)
        maskname = os.path.splitext(os.path.split(self._filename)[1])[0]
        savemat(self._filename, {maskname: self._mask})

    def on_saveas(self, button):
        if not hasattr(self, '_filechooser'):
            self._filechooser = Gtk.FileChooserDialog('Save mask file...',
                                                      self._window,
                                                      Gtk.FileChooserAction.SAVE,
                                                      ['Save', 1, 'Cancel', 0])
            self._filechooser.set_do_overwrite_confirmation(True)
            self._filefilter = Gtk.FileFilter()
            self._filefilter.add_pattern('*.mat')
            self._filefilter.set_name('Mask files')
            self._filechooser.add_filter(self._filefilter)
        self._filechooser.set_action(Gtk.FileChooserAction.SAVE)
        self._filechooser.get_widget_for_response(1).set_label('Save')
        if self._filechooser.run() == 1:
            self._filename = self._filechooser.get_filename()
            self.on_save(button)
        self._filechooser.hide()

    def on_selectcircle_toggled(self, button):
        pass

    def on_selectrectangle_toggled(self, button):
        pass

    def on_selectpolygon_toggled(self, button):
        pass

    def on_mask_toggled(self, button):
        pass

    def on_unmask_toggled(self, button):
        pass

    def on_invertmask_toggled(self, button):
        pass

    def on_pixelhunting_toggled(self, button):
        pass
