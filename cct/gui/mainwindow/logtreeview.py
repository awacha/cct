import logging
import os

import pkg_resources
from gi.repository import Gtk

from ..core.builderwidget import BuilderWidget


class LogTreeView(BuilderWidget):
    def __init__(self):
        self.nentries = None
        self.filterlevel = logging.NOTSET
        super().__init__(pkg_resources.resource_filename(
            'cct', os.path.join('resource', 'glade', 'core_logtree.glade')), 'logtreeview')
        filter = self.builder.get_object('logstore_filtered')
        assert isinstance(filter, Gtk.TreeModelFilter)
        filter.set_visible_column(7)
        flc = self.builder.get_object('filterlevel_combo')
        assert isinstance(flc, Gtk.ComboBoxText)
        flc.remove_all()
        for i in range(0, 100):
            l = logging.getLevelName(i)
            if not l.startswith('Level '):
                flc.append(str(i), l)
        flc.set_active(0)

    def on_filterlevel_changed(self, cb: Gtk.ComboBoxText):
        try:
            self.filterlevel = int(cb.get_active_id())
        except TypeError:
            return
        model = self.builder.get_object('logstore')
        assert isinstance(model, Gtk.ListStore)
        for row in model:
            row[7] = row[2] >= self.filterlevel

    def on_nentries_changed(self, spinbutton: Gtk.SpinButton):
        self.nentries = spinbutton.get_value_as_int()
        model = self.builder.get_object('logstore')
        while len(model) > self.nentries:
            model.remove(model.get_iter_first())

    def add_logentry(self, record: logging.LogRecord):
        model = self.builder.get_object('logstore')
        assert isinstance(model, Gtk.ListStore)
        if record.levelno == logging.DEBUG:
            textcolor = 'gray'
            bgcolor = 'white'
        elif record.levelno == logging.INFO:
            textcolor = 'black'
            bgcolor = 'white'
        elif record.levelno == logging.WARNING:
            textcolor = 'yellow'
            bgcolor = 'white'
        elif record.levelno == logging.ERROR:
            textcolor = 'red'
            bgcolor = 'white'
        elif record.levelno == logging.CRITICAL:
            textcolor = 'black'
            bgcolor = 'red'
        else:
            textcolor = 'blue'
            bgcolor = 'white'
        it = model.append(
            [record.asctime, record.levelname, record.levelno, '{}:{:d}'.format(record.name, record.lineno),
             record.getMessage(), textcolor, bgcolor, record.levelno >= self.filterlevel])
        if self.builder.get_object('autoscroll_checkbutton').get_active():
            filteredmodel = self.builder.get_object('logstore_filtered')
            assert isinstance(filteredmodel, Gtk.TreeModelFilter)
            success, it = filteredmodel.convert_child_iter_to_iter(it)
            if success:
                self.builder.get_object('logview').scroll_to_cell(filteredmodel.get_path(it), None, True, 0.0, 1.0)
