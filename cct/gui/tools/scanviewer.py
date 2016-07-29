from ..core.functions import update_comboboxtext_choices
from ..core.scangraph import ScanGraph
from ..core.toolwindow import ToolWindow


class ScanViewer(ToolWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._selected_scanfile = None  # keep a separate account in order to avoid refreshing the whole list
        self._lastscanconnection = None

    def init_gui(self, *args, **kwargs):
        pass

    def cleanup(self):
        self.instrument.services['filesequence'].disconnect(self._lastscanconnection)
        self._lastscanconnection = None

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self.update_gui()
        self._lastscanconnection = self.instrument.services['filesequence'].connect('lastscan-changed',
                                                                                    self.on_lastscan_changed)

    def update_gui(self):
        update_comboboxtext_choices(self.builder.get_object('scanfile_selector'),
                                    sorted(self.instrument.services['filesequence'].get_scanfiles()),
                                    default=self.instrument.services['filesequence'].get_scanfile())

    def on_scanfile_changed(self, scanfileselector):
        scanfile = scanfileselector.get_active_text()
        if (scanfile == self._selected_scanfile) or (scanfile is None):
            # do not reload the scanfile if it is already loaded.
            return
        self._selected_scanfile = scanfile
        scans = self.instrument.services['filesequence'].get_scans(scanfileselector.get_active_text())
        model = self.builder.get_object('scanstore')
        model.clear()
        for idx in sorted(scans):
            model.append((idx, scans[idx]['cmd'], str(scans[idx]['date']), scans[idx]['comment']))

    def on_scanview_row_activated(self, scanview, path, column):
        self.on_open(None)

    def on_open(self, button):
        model, iterators = self.builder.get_object('scanview').get_selection().get_selected_rows()
        for iterator in iterators:
            idx = model[iterator][0]
            scan = self.instrument.services['filesequence'].load_scan(idx, self.builder.get_object(
                'scanfile_selector').get_active_text())
            sg = ScanGraph(scan['signals'], scan['data'], idx, scan['comment'], self.instrument)
            sg.widget.show_all()

    def on_lastscan_changed(self, filesequence, lastscan):
        scanfileselector = self.builder.get_object('scanfile_selector')
        model = self.builder.get_object('scanstore')
        scans = self.instrument.services['filesequence'].get_scans(scanfileselector.get_active_text())
        model.append((lastscan, scans[lastscan]['cmd'], str(scans[lastscan]['date']), scans[lastscan]['comment']))

    def reload_scans(self, button):
        self.instrument.services['filesequence'].load_scanfile_toc()
        self.update_gui()
