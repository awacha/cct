import datetime
import logging

from ..core.dialogs import question_message
from ..core.toolwindow import ToolWindow
from ...core.services.samples import Sample, ErrorValue

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SampleEdit(ToolWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sampleconnections = []
        self._changedselection = None

    def cleanup(self):
        for c in self._sampleconnections:
            self.instrument.services['samplestore'].disconnect(c)
        self._sampleconnections = []

    def on_mainwidget_map(self, window):
        if super().on_mainwidget_map(window):
            return True
        self._sampleconnections = [
            self.instrument.services['samplestore'].connect('list-changed', lambda x: self.repopulate_list())]
        self.repopulate_list()

    def on_new(self, button):
        newsample = Sample('Unnamed')
        if not self.instrument.services['samplestore'].add(newsample):
            index = 1
            while not self.instrument.services['samplestore'].add(Sample('Unnamed_%d' % index)):
                index += 1

    def on_duplicate(self, button):
        model, it = self.builder.get_object('sampletreeview').get_selection().get_selected()
        selectedname = model[it][0]
        selectedsample = [s for s in self.instrument.services['samplestore'] if s.title == selectedname]
        assert (len(selectedsample) == 1)
        newsample = Sample(selectedsample[0])
        newsample.title += '_copy'
        index = 1
        while not self.instrument.services['samplestore'].add(newsample):
            newsample.title = selectedsample[0].title + '_copy%d' % index
            index += 1

    def on_edit(self, widget):
        model, it = self.builder.get_object('sampletreeview').get_selection().get_selected()
        self._changedselection = model[it][0]
        self.builder.get_object('apply_button').set_sensitive(True)

    def on_remove(self, button):
        model, it = self.builder.get_object('sampletreeview').get_selection().get_selected()
        self.instrument.services['samplestore'].remove(model[it][0])

    def repopulate_list(self):
        model = self.builder.get_object('samplestore')
        tv = self.builder.get_object('sampletreeview')
        model, it = tv.get_selection().get_selected()
        if it is not None:
            previously_selected = model[it][0]
        else:
            previously_selected = self.instrument.services['samplestore'].get_active_name()
        model.clear()
        for s in sorted(self.instrument.services['samplestore'], key=lambda x: x.title):
            model.append((s.title,))
        it = model.get_iter_first()
        while it:
            if not model[it][
                0] < previously_selected:  # relational operators between strings mean alphatbetical ordering
                tv.get_selection().select_iter(it)
                break
            it = model.iter_next(it)

    def on_select(self, treeselection):
        if self._changedselection is not None:
            if question_message(self.widget, 'Save changes?',
                                'Do you want to save the changes you made to sample "%s"?' % self._changedselection):
                self.save_changes()
        model, it = treeselection.get_selected()
        if it is None:
            return
        selectedname = model[it][0]
        try:
            sample = self.instrument.services['samplestore'].get_sample(selectedname)
        except KeyError:
            self.repopulate_list()
            return
        self.builder.get_object('title_entry').set_text(sample.title)
        self.builder.get_object('description_entry').set_text(sample.description)
        self.builder.get_object('preparedby_entry').set_text(sample.preparedby)

        active_set = False
        for i, row in enumerate(self.builder.get_object('category_combo').get_model()):
            if row[0] == sample.category:
                self.builder.get_object('category_combo').set_active(i)
                active_set = True
                break
        if not active_set:
            logger.error('Sample category *%s* is not in category_combo (%s)' % (sample.category,
                                                                                 ', '.join(str("*" + r[0] + "*" for r in
                                                                                               self.builder.get_object(
                                                                                                   'category_combo').get_model()))))

        active_set = False
        for i, row in enumerate(self.builder.get_object('situation_combo').get_model()):
            if row[0] == sample.situation:
                self.builder.get_object('situation_combo').set_active(i)
                active_set = True
                break
        if not active_set:
            logger.error('Sample situation %s is not in situation_combo (%s)' % (sample.situation,
                                                                                 ', '.join(r[0] for r in
                                                                                           self.builder.get_object(
                                                                                               'situation_combo').get_model())))

        self.builder.get_object('thicknessval_spin').set_value(sample.thickness.val)
        self.builder.get_object('thicknesserr_spin').set_value(sample.thickness.err)
        self.builder.get_object('positionxval_spin').set_value(sample.positionx.val)
        self.builder.get_object('positionxerr_spin').set_value(sample.positionx.err)
        self.builder.get_object('positionyval_spin').set_value(sample.positiony.val)
        self.builder.get_object('positionyerr_spin').set_value(sample.positiony.err)
        self.builder.get_object('distminusval_spin').set_value(sample.distminus.val)
        self.builder.get_object('distminuserr_spin').set_value(sample.distminus.err)
        self.builder.get_object('transmissionval_spin').set_value(sample.transmission.val)
        self.builder.get_object('transmissionerr_spin').set_value(sample.transmission.err)
        self.builder.get_object('preparetime_calendar').select_month(sample.preparetime.month - 1,
                                                                     sample.preparetime.year)
        self.builder.get_object('preparetime_calendar').select_day(sample.preparetime.day)
        self.builder.get_object('apply_button').set_sensitive(False)
        self._changedselection = None

    def save_changes(self):
        if self._changedselection is None:
            return
        date = self.builder.get_object('preparetime_calendar').get_date()
        date = datetime.date(date[0], date[1] + 1, date[2])
        sample = Sample(self.builder.get_object('title_entry').get_text(),
                        ErrorValue(self.builder.get_object('positionxval_spin').get_value(),
                                   self.builder.get_object('positionxerr_spin').get_value()),
                        ErrorValue(self.builder.get_object('positionyval_spin').get_value(),
                                   self.builder.get_object('positionyerr_spin').get_value()),
                        ErrorValue(self.builder.get_object('thicknessval_spin').get_value(),
                                   self.builder.get_object('thicknesserr_spin').get_value()),
                        ErrorValue(self.builder.get_object('transmissionval_spin').get_value(),
                                   self.builder.get_object('transmissionerr_spin').get_value()),
                        self.builder.get_object('preparedby_entry').get_text(),
                        date,
                        ErrorValue(self.builder.get_object('distminusval_spin').get_value(),
                                   self.builder.get_object('distminuserr_spin').get_value()),
                        self.builder.get_object('description_entry').get_text(),
                        self.builder.get_object('category_combo').get_active_text(),
                        self.builder.get_object('situation_combo').get_active_text()
                        )
        oldtitle = self._changedselection
        self._changedselection = None
        self.instrument.services['samplestore'].set_sample(oldtitle, sample)
        self.builder.get_object('apply_button').set_sensitive(False)
        self.instrument.save_state()

    def on_apply(self, button):
        self.save_changes()
