import datetime
import logging

from gi.repository import Gtk

from ..core.toolwindow import ToolWindow, question_message
from ...core.instrument.sample import Sample, ErrorValue

logger=logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class SampleEdit(ToolWindow):
    def _init_gui(self):
        tc=Gtk.TreeViewColumn('Sample',Gtk.CellRendererText(), text=0)
        tc.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self._builder.get_object('sampletreeview').append_column(tc)

    def _break_connections(self):
        try:
            for c in self._sampleconnections:
                self._instrument.samplestore.disconnect(c)
            del self._sampleconnections
        except AttributeError:
            pass

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self._break_connections()
        self._sampleconnections=[self._instrument.samplestore.connect('list-changed', lambda x: self._repopulate_list())]
        self._repopulate_list()

    def on_unmap(self, window):
        self._break_connections()
        pass

    def on_new(self, button):
        newsample=Sample('Unnamed')
        if not self._instrument.samplestore.add(newsample):
            index=1
            while not self._instrument.samplestore.add(Sample('Unnamed_%d'%index)):
                index+=1

    def on_duplicate(self, button):
        model, it=self._builder.get_object('sampletreeview').get_selection().get_selected()
        selectedname=model[it][0]
        selectedsample=[s for s in self._instrument.samplestore if s.title==selectedname]
        assert(len(selectedsample)==1)
        newsample=Sample(selectedsample[0])
        newsample.title=newsample.title+'_copy'
        index=1
        while not self._instrument.samplestore.add(newsample):
            newsample.title=selectedsample[0].title+'_copy%d'%index
            index +=1

    def on_edit(self, widget):
        model, it=self._builder.get_object('sampletreeview').get_selection().get_selected()
        self._changedselection=model[it][0]
        self._builder.get_object('apply_button').set_sensitive(True)

    def on_remove(self, button):
        model, it=self._builder.get_object('sampletreeview').get_selection().get_selected()
        self._instrument.samplestore.remove(model[it][0])

    def _repopulate_list(self):
        model=self._builder.get_object('samplestore')
        tv=self._builder.get_object('sampletreeview')
        model, it=tv.get_selection().get_selected()
        if it is not None:
            previously_selected=model[it][0]
        else:
            previously_selected=self._instrument.samplestore.get_active_name()
        model.clear()
        for s in sorted(self._instrument.samplestore, key=lambda x:x.title):
            model.append((s.title,))
        it=model.get_iter_first()
        while it:
            if not model[it][0] < previously_selected: # relational operators between strings mean alphatbetical ordering
                tv.get_selection().select_iter(it)
                break
            it=model.iter_next(it)

    def on_select(self, treeselection):
        if hasattr(self, '_changedselection'):
            if question_message(self._window, 'Save changes?',
                                'Do you want to save the changes you made to sample "%s"?'%self._changedselection):
                self._save_changes()
        model, it=treeselection.get_selected()
        if it is None:
            return
        selectedname=model[it][0]
        try:
            sample=self._instrument.samplestore.get_sample(selectedname)
        except KeyError:
            self._repopulate_list()
            return
        self._builder.get_object('title_entry').set_text(sample.title)
        self._builder.get_object('description_entry').set_text(sample.description)
        self._builder.get_object('preparedby_entry').set_text(sample.preparedby)

        active_set=False
        for i,row in enumerate(self._builder.get_object('category_combo').get_model()):
            if row[0]==sample.category:
                self._builder.get_object('category_combo').set_active(i)
                active_set=True
                break
        if not active_set:
            logger.error('Sample category *%s* is not in category_combo (%s)'%(sample.category,
                ', '.join(str("*"+r[0]+"*" for r in self._builder.get_object('category_combo').get_model()))))

        active_set=False
        for i,row in enumerate(self._builder.get_object('situation_combo').get_model()):
            if row[0]==sample.situation:
                self._builder.get_object('situation_combo').set_active(i)
                active_set=True
                break
        if not active_set:
            logger.error('Sample situation %s is not in situation_combo (%s)'%(sample.situation,
                ', '.join(r[0] for r in self._builder.get_object('situation_combo').get_model())))

        self._builder.get_object('thicknessval_spin').set_value(sample.thickness.val)
        self._builder.get_object('thicknesserr_spin').set_value(sample.thickness.err)
        self._builder.get_object('positionxval_spin').set_value(sample.positionx.val)
        self._builder.get_object('positionxerr_spin').set_value(sample.positionx.err)
        self._builder.get_object('positionyval_spin').set_value(sample.positiony.val)
        self._builder.get_object('positionyerr_spin').set_value(sample.positiony.err)
        self._builder.get_object('distminusval_spin').set_value(sample.distminus.val)
        self._builder.get_object('distminuserr_spin').set_value(sample.distminus.err)
        self._builder.get_object('transmissionval_spin').set_value(sample.transmission.val)
        self._builder.get_object('transmissionerr_spin').set_value(sample.transmission.err)
        self._builder.get_object('preparetime_calendar').select_month(sample.preparetime.month,
                                                                      sample.preparetime.year)
        self._builder.get_object('preparetime_calendar').select_day(sample.preparetime.day)
        try:
            self._builder.get_object('apply_button').set_sensitive(False)
            del self._changedselection
        except AttributeError:
            pass

    def _save_changes(self):
        if not hasattr(self, '_changedselection'):
            return
        sample=Sample(self._builder.get_object('title_entry').get_text(),
                      ErrorValue(self._builder.get_object('positionxval_spin').get_value(),
                                 self._builder.get_object('positionxerr_spin').get_value()),
                      ErrorValue(self._builder.get_object('positionyval_spin').get_value(),
                                 self._builder.get_object('positionyerr_spin').get_value()),
                      ErrorValue(self._builder.get_object('thicknessval_spin').get_value(),
                                 self._builder.get_object('thicknesserr_spin').get_value()),
                      ErrorValue(self._builder.get_object('transmissionval_spin').get_value(),
                                 self._builder.get_object('transmissionerr_spin').get_value()),
                      self._builder.get_object('preparedby_entry').get_text(),
                      datetime.date(*self._builder.get_object('preparetime_calendar').get_date()),
                      ErrorValue(self._builder.get_object('distminusval_spin').get_value(),
                                 self._builder.get_object('distminuserr_spin').get_value()),
                      self._builder.get_object('description_entry').get_text(),
                      self._builder.get_object('category_combo').get_active_text(),
                      self._builder.get_object('situation_combo').get_active_text()
                      )
        oldtitle=self._changedselection
        del self._changedselection
        self._instrument.samplestore.set_sample(oldtitle,sample)
        self._builder.get_object('apply_button').set_sensitive(False)
        self._instrument.save_state()

    def on_apply(self, button):
        self._save_changes()