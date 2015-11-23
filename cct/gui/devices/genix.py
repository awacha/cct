import logging

from ..core.indicator import Indicator, IndicatorState
from ..core.toolwindow import ToolWindow, question_message

logger=logging.getLogger(__name__)
logger.setlevel(logging.INFO)


class GeniX(ToolWindow):
    def _init_gui(self, *args):
        self._indicators={}
        statusindicators=self._builder.get_object('statusindicators')
        for row, column, vn,label in [(0, 0, '_status', 'Status'), (0, 1, 'ht', 'Tube voltage'),
                                      (0, 2, 'current', 'Tube current'), (0,3, 'power','Power'),
                         (0,4, 'tubetime', 'Tube on-time'), (1,0,'remote_mode', 'Remote control'),
                         (1,1,'xrays','X-ray generator'), (1,2,'shutter', 'Shutter'),
                         (1,3,'interlock', 'Interlock'), (1,4,'overridden','Override mode')]:
            self._indicators[vn]=Indicator(label, 'N/A', IndicatorState.UNKNOWN)
            statusindicators.attach(self._indicators[vn],column, row,1,1)
        errorindicators=self._builder.get_object('errorindicators')
        for row, column, vn, label in [(0,0,'faults','Faults present'),
                                       (0,1,'xray_light_fault', 'X-rays on light'),
                                       (0,2,'shutter_light_fault', 'Shutter open light'),
                                       (0,3,'vacuum_fault', 'Optics vacuum'),
                                       (0,4,'waterflow_fault', 'Water cooling'),
                                       (1,0,'tube_position_fault', 'Tube in place'),
                                       (1,1,'filament_fault', 'Tube filament'),
                                       (1,2,'safety_shutter_fault', 'Safety shutter'),
                                       (1,3,'sensor1_fault', 'Sensor #1'),
                                       (1,4,'sensor2_fault', 'Sensor #2'),
                                       (2,0,'temperature_fault', 'Tube temperature'),
                                       (2,1,'relay_interlock_fault', 'Interlock relays'),
                                       (2,2,'door_fault', 'Interlock system'),
                                       (2,3,'tube_warmup_needed', 'Warm-up')]:
            self._indicators[vn]=Indicator(label, 'N/A', IndicatorState.UNKNOWN)
            errorindicators.attach(self._indicators[vn],column, row,1,1)
        self._genix=self._instrument.devices['genix']
        self._update_indicators()

    def on_map(self, window):
        if ToolWindow.on_map(self, window):
            return True
        self._update_indicators()
        if not hasattr(self, '_genixconnections'):
            self._genixconnections = [self._genix.connect('variable-change', self.on_variable_change),
                                      ]

    def _update_indicators(self):
        for vn in self._indicators:
            self.on_variable_change(self._genix, vn, self._genix.get_variable(vn))
        genixshutter = self._genix.get_variable('shutter')
        shuttertoggle = self._builder.get_object('shutter_toggle').get_active()
        if genixshutter != shuttertoggle:
            self._builder.get_object('shutter_toggle').set_active(self._genix.get_variable('shutter'))
        genixxrays = self._genix.get_variable('xrays')
        xraystoggle = self._builder.get_object('xraystate_toggle').get_active()
        if genixxrays != xraystoggle:
            self._builder.get_object('xraystate_toggle').set_active(self._genix.get_variable('xrays'))

    def on_unmap(self, window):
        try:
            for c in self._genixconnections:
                self._genix.disconnect(c)
            del self._genixconnections
        except AttributeError:
            pass

    def on_warmup(self, button):
        if button.get_active():
            try:
                if self._genix.get_variable('_status')=='Power off':
                    self._genix.execute_command('start_warmup')
                else:
                    logger.error('Cannot start warm-up procedure unless the X-ray source is in "Power off" state.')
            except:
                button.set_active(False)
                raise
        else:
            if (not self._genix.get_variable('_status')=='Warming up') or (question_message('Do you really want to break the warm-up sequence?', 'Voltage will be gradually decreased to 0 kV.')):
                self._genix.execute_command('stop_warmup')

    def on_resetfaults(self, button):
        self._genix.execute_command('reset_faults')

    def on_poweroff(self, button):
        self._genix.execute_command('poweroff')

    def on_standby(self, button):
        self._genix.execute_command('standby')
        pass

    def on_shutter(self, button):
        logger.debug('Shutter button toggled to: ' + str(button.get_active()))
        if self._genix.get_variable('shutter') != button.get_active():
            self._genix.execute_command('shutter', button.get_active())

    def on_xraystate(self, button):
        self._genix.execute_command('xrays',button.get_active())

    def on_fullpower(self, button):
        self._genix.execute_command('full_power')

    def on_variable_change(self, genix, variablename, newvalue):
        if variablename=='_status':
            self._indicators[variablename].set_value(newvalue, IndicatorState.NEUTRAL)
            powerbuttons={'down':self._builder.get_object('powerdown_button'),
                          'standby':self._builder.get_object('standby_button'),
                          'full':self._builder.get_object('fullpower_button'),
                          'warmup':self._builder.get_object('warmup_toggle'),
                          }
            xraybutton=self._builder.get_object('xraystate_toggle')
            shutterbutton=self._builder.get_object('shutter_toggle')
            xraybutton.set_sensitive(False) # prime it to insensitive. If we are in power off state, only then can this be sensitive.
            if newvalue=='Power off':
                for b in powerbuttons:
                    powerbuttons[b].set_sensitive(True)
                powerbuttons['down'].set_sensitive(False)
                xraybutton.set_sensitive(True)
            elif newvalue==['Powering down', 'Ramping up', 'Going to stand-by']:
                for b in powerbuttons:
                    powerbuttons[b].set_sensitive(False)
            elif newvalue in ['Warming up']:
                for b in powerbuttons:
                    powerbuttons[b].set_sensitive(False)
                powerbuttons['warmup'].set_sensitive(True)
            elif newvalue=='Low power':
                for b in powerbuttons:
                    powerbuttons[b].set_sensitive(False)
                powerbuttons['full'].set_sensitive(True)
                powerbuttons['down'].set_sensitive(True)
            elif newvalue=='Full power':
                for b in powerbuttons:
                    powerbuttons[b].set_sensitive(False)
                powerbuttons['standby'].set_sensitive(True)
                powerbuttons['down'].set_sensitive(True)
            elif newvalue=='X-rays off':
                for b in powerbuttons:
                    powerbuttons[b].set_sensitive(False)
                xraybutton.set_sensitive(True)
        elif variablename=='ht':
            self._indicators[variablename].set_value('%.1f kV'%newvalue, IndicatorState.NEUTRAL)
        elif variablename=='current':
            self._indicators[variablename].set_value('%.1f mA'%newvalue, IndicatorState.NEUTRAL)
        elif variablename=='power':
            self._indicators[variablename].set_value('%.1f W'%newvalue, IndicatorState.NEUTRAL)
        elif variablename=='tubetime':
            self._indicators[variablename].set_value('%.2f h / %.2f days'%(newvalue, newvalue/24), IndicatorState.NEUTRAL)
        elif variablename=='remote_mode':
            self._indicators[variablename].set_value(['No','Yes'][newvalue], [IndicatorState.ERROR,IndicatorState.OK][newvalue])
            if newvalue:
                self._make_sensitive()
            else:
                self._make_insensitive(None, ['operations_buttonbox', 'statusindicators', 'errorindicators'])
        elif variablename=='xrays':
            self._indicators[variablename].set_value(['Off','On'][newvalue], [IndicatorState.ERROR,IndicatorState.OK][newvalue])
            xraystate_toggle = self._builder.get_object('xraystate_toggle')
            if xraystate_toggle.get_active()!=newvalue:
                xraystate_toggle.set_active(newvalue)
            if not newvalue:
                xraystate_toggle.set_sensitive(True)
        elif variablename=='shutter':
            self._indicators[variablename].set_value(['Open','Closed'][not newvalue], [IndicatorState.ERROR,IndicatorState.OK][not newvalue])
            shutter_toggle=self._builder.get_object('shutter_toggle')
            if shutter_toggle.get_active()!=newvalue:
                shutter_toggle.set_active(newvalue)
        elif variablename=='interlock':
            self._indicators[variablename].set_value(['Broken','Set'][newvalue], [IndicatorState.ERROR,IndicatorState.OK][newvalue])
        elif variablename=='overridden':
            self._indicators[variablename].set_value(['Active','No'][not newvalue], [IndicatorState.ERROR,IndicatorState.OK][not newvalue])
        elif variablename=='faults':
            self._builder.get_object('resetfaults_button').set_sensitive(newvalue)
            self._indicators[variablename].set_value(['Present', 'None'][not newvalue], [IndicatorState.ERROR,IndicatorState.OK][not newvalue])
        elif variablename in ['xray_light_fault', 'shutter_light_fault', 'filament_fault', 'safety_shutter_fault',
                              'sensor1_fault', 'sensor2_fault', 'vacuum_fault', 'waterflow_fault', 'relay_interlock_fault', 'door_fault']:
            self._indicators[variablename].set_value(['Broken', 'Working'][not newvalue],
                                                     [IndicatorState.ERROR,IndicatorState.OK][not newvalue])
        elif variablename=='tube_position_fault':
            self._indicators[variablename].set_value(['Missing', 'Yes'][not newvalue],
                                                     [IndicatorState.ERROR,IndicatorState.OK][not newvalue])
        elif variablename=='temperature_fault':
            self._indicators[variablename].set_value(['Overheating','OK'][not newvalue],
                                                     [IndicatorState.ERROR,IndicatorState.OK][not newvalue])
        elif variablename=='tube_warmup_needed':
            self._indicators[variablename].set_value(['Needed','Not needed'][not newvalue],
                                                     [IndicatorState.ERROR,IndicatorState.OK][not newvalue])
