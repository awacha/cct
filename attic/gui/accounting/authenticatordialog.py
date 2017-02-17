import pkg_resources

from gi.repository import Gtk


class AuthenticatorDialog(object):
    def __init__(self, instrument):
        self.application = Gtk.Application.get_default()
        self.instrument = instrument
        self.builder = Gtk.Builder.new_from_file(
            pkg_resources.resource_filename('cct', 'resource/glade/accounting_login.glade'))
        self.widget = self.builder.get_object('accountingdialog')
        # initialize the CSS style provider for Gtk3
        cssprovider = Gtk.CssProvider()
        cssprovider.load_from_path(pkg_resources.resource_filename('cct', 'resource/css/widgetbackgrounds.css'))
        self.builder.get_object('password_entry').get_style_context().add_provider(cssprovider,
                                                                                   Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self.builder.connect_signals(self)

    # noinspection PyMethodMayBeStatic
    def on_password_changed(self, password_entry):
        password_entry.set_name('GtkEntry')

    def run(self, skip_authentication=False):
        if skip_authentication:
            try:
                self.instrument.services['accounting'].current_user = [
                    u for u in self.instrument.services['accounting'].users if u.username == 'root'][0]
                self.instrument.services['accounting'].set_privilegelevel(
                    self.instrument.services['accounting'].current_user.privlevel)
                return True
            except IndexError:
                raise ValueError('Tried to skip authentication but no root account present.')
        while True:
            response = self.widget.run()
            if response == Gtk.ResponseType.DELETE_EVENT or response == 0:
                self.application.quit()
                return False
            elif response == 1:
                username = self.builder.get_object('operator_entry').get_text()
                if self.instrument.services['accounting'].authenticate(
                        username, self.builder.get_object('password_entry').get_text()):
                    return True
                self.builder.get_object('password_entry').set_name('redbackground')
