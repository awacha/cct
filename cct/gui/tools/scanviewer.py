from ..core.scangraph import ScanGraph
from ..core.toolwindow import ToolWindow


class ScanViewer(ToolWindow):
    def _init_gui(self, *args):
        self._selected_scanfile = None  # keep a separate account in order to avoid refreshing the whole list

    def _disconnect_lastscanconnection(self):
        try:
            self._instrument.filesequence.disconnect(self._lastscanconnection)
            del self._lastscanconnection
        except AttributeError:
            pass

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self._update_gui()

    def _update_gui(self):
        self._disconnect_lastscanconnection()
        self._lastscanconnection = self._instrument.filesequence.connect('lastscan-changed', self.on_lastscan_changed)
        scanfileselector = self._builder.get_object('scanfile_selector')
        scanfileselector.set_active(-1)
        scanfileselector.remove_all()
        self._selected_scanfile = None
        for i, sf in enumerate(sorted(self._instrument.filesequence.get_scanfiles())):
            scanfileselector.append_text(sf)
            if sf == self._selected_scanfile:
                scanfileselector.set_active(i)
        if scanfileselector.get_active_text() is None:
            scanfileselector.set_active(0)

    def on_unmap(self, window):
        self._disconnect_lastscanconnection()

    def on_scanfile_changed(self, scanfileselector):
        scanfile = scanfileselector.get_active_text()
        if (scanfile == self._selected_scanfile) or (scanfile is None):
            return
        self._selected_scanfile = scanfile
        scans = self._instrument.filesequence.get_scans(scanfileselector.get_active_text())
        model = self._builder.get_object('scanstore')
        model.clear()
        for idx in sorted(scans):
            model.append((idx, scans[idx]['cmd'], str(scans[idx]['date']), scans[idx]['comment']))

    def on_scanview_row_activated(self, scanview, path, column):
        self.on_open(None)

    def on_open(self, button):
        model, iterators = self._builder.get_object('scanview').get_selection().get_selected_rows()
        for iterator in iterators:
            idx = model[iterator][0]
            scan = self._instrument.filesequence.load_scan(idx, self._builder.get_object(
                'scanfile_selector').get_active_text())
            sg = ScanGraph(scan['signals'], scan['data'], self._instrument, idx, scan['comment'])
            sg._window.show_all()

    def on_lastscan_changed(self, filesequence, lastscan):
        scanfileselector = self._builder.get_object('scanfile_selector')
        model = self._builder.get_object('scanstore')
        scans = self._instrument.filesequence.get_scans(scanfileselector.get_active_text())
        model.append((lastscan, scans[lastscan]['cmd'], str(scans[lastscan]['date']), scans[lastscan]['comment']))
