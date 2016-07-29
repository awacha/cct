import os

from gi.repository import Gtk


class DoubleFileChooserDialog:
    def __init__(self, mainwindow, loadtitle, savetitle, filters=None, initial_folder=None, shortcut_folders=None):
        if initial_folder is None:
            initial_folder = os.getcwd()
        if shortcut_folders is None:
            shortcut_folders = []
        fco = Gtk.FileChooserDialog(parent=mainwindow, action=Gtk.FileChooserAction.OPEN, title=loadtitle)
        fco.add_buttons('Open', 1, 'Cancel', 0)
        fcs = Gtk.FileChooserDialog(parent=mainwindow, action=Gtk.FileChooserAction.SAVE, title=savetitle)
        fcs.add_buttons('Open', 1, 'Cancel', 0)
        fs = []
        for name, pattern in filters:
            fs.append(Gtk.FileFilter())
            fs[-1].set_name(name)
            if isinstance(pattern, str):
                fs[-1].add_pattern(pattern)
            else:
                for p in pattern:
                    fs[-1].add_pattern(p)
        for d in [fco, fcs]:
            b = d.get_widget_for_response(1)
            assert isinstance(b, Gtk.Button)
            b.set_can_default(True)
            b.grab_default()
            for f in fs:
                d.add_filter(f)
            d.set_filter(fs[0])
            d.set_current_folder(initial_folder)
            for sf in shortcut_folders:
                d.add_shortcut_folder(sf)
        self.__dfcd = {'opendialog': fco, 'savedialog': fcs, 'filters': fs, 'last_filename': None}

    def get_open_filename(self):
        if self.__dfcd['last_filename'] is not None:
            self.__dfcd['opendialog'].set_current_folder(os.path.split(self.__dfcd['last_filename'])[0])
        try:
            if self.__dfcd['opendialog'].run() == 1:
                self.__dfcd['last_filename'] = self.__dfcd['opendialog'].get_filename()
                return self.__dfcd['last_filename']
        finally:
            self.__dfcd['opendialog'].hide()

    def get_save_filename(self, suggested_name=None):
        if self.__dfcd['last_filename'] is not None:
            self.__dfcd['savedialog'].set_current_folder(os.path.split(self.__dfcd['last_filename'])[0])
        if suggested_name is None:
            if self.__dfcd['last_filename'] is not None:
                suggested_name = os.path.split(self.__dfcd['last_filename'])[1]
            else:
                suggested_name = self.suggest_filename()
        self.__dfcd['savedialog'].set_current_name(suggested_name)
        try:
            if self.__dfcd['savedialog'].run() == 1:
                self.__dfcd['last_filename'] = self.__dfcd['savedialog'].get_filename()
                return self.__dfcd['last_filename']
        finally:
            self.__dfcd['savedialog'].hide()

    def get_last_filename(self):
        return self.__dfcd['last_filename']

    def set_last_filename(self, filename):
        if (filename is not None) and (not os.path.isabs(filename)):
            filename = os.path.abspath(filename)
        self.__dfcd['last_filename'] = filename

    def suggest_filename(self):
        return 'untitled'
