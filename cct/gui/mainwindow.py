from gi.repository import Gtk, Gio


class CCTApplication(Gtk.Application):

    def __init__(self, *args, **kwargs):
        Gtk.Application.__init__(self, *args, **kwargs)
        self.connect('activate', self.on_activate)
        self.connect('startup', self.on_startup)

    def on_startup(self, app):
        self._init_menu()

    def on_activate(self, app):
        mw = MainWindow(application=self)
        self.add_window(mw)
        return True

    def _init_menu(self):
        menu = Gio.Menu()
        filemenu = Gio.Menu()
        menu.insert_submenu(position=0, label='_File', submenu=filemenu)
        filemenu.append('_Save settings')
        filemenu.append('_Quit')
        setupmenu = Gio.Menu()
        menu.insert_submenu(position=1, label='_Setup', submenu=setupmenu)
        setupmenu.append('_Centering')
        setupmenu.append('_Distance calibration')

#        self.set_app_menu(menu)
        self.set_menubar(menu)


class MainWindow(Gtk.ApplicationWindow):

    def __init__(self, *args, **kwargs):
        Gtk.ApplicationWindow.__init__(self, *args, **kwargs)
        self.set_show_menubar(True)
        self.add(Gtk.Button(label='Test'))
        self.show_all()

if __name__ == '__main__':
    app = CCTApplication(
        application_id='hu.mta.ttk.credo.cctgui', flags=Gio.ApplicationFlags.FLAGS_NONE)
    app.run()
