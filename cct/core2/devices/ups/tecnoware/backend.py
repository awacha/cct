import re
from math import inf
from typing import Tuple, List

from ...device.backend import DeviceBackend


class TecnowareEvoDSPPlusBackend(DeviceBackend):
    class Status(DeviceBackend.Status):
        GridPower = 'grid'
        BatteryPower = 'battery'

    varinfo = [
        # query with b'QPI\r'
        DeviceBackend.VariableInfo(name='protocolID', timeout=inf),
        # query the following variables with b'QMD\r'
        DeviceBackend.VariableInfo(name='modelname', timeout=inf),
        DeviceBackend.VariableInfo(name='ratedVA', dependsfrom=['modelname'], timeout=inf),
        DeviceBackend.VariableInfo(name='powerfactor', dependsfrom=['modelname'], timeout=inf),  # may be volatile?
        DeviceBackend.VariableInfo(name='inputphasecount', dependsfrom=['modelname'], timeout=inf),
        DeviceBackend.VariableInfo(name='outputphasecount', dependsfrom=['modelname'], timeout=inf),
        DeviceBackend.VariableInfo(name='nominalinputvoltage', dependsfrom=['modelname'], timeout=inf),
        DeviceBackend.VariableInfo(name='nominaloutputvoltage', dependsfrom=['modelname'], timeout=inf),
        DeviceBackend.VariableInfo(name='batterycount', dependsfrom=['modelname'], timeout=inf),
        DeviceBackend.VariableInfo(name='nominalbatteryvoltage', dependsfrom=['modelname'], timeout=inf),

        # query the following variables with b'QGS\r'
        DeviceBackend.VariableInfo(name='inputvoltage', timeout=1.0),
        DeviceBackend.VariableInfo(name='inputfrequency', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='outputvoltage', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='outputfrequency', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='outputcurrent', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='outputloadpercentage', dependsfrom=['inputvoltage'],
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='positiveBUSvoltage', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='negativeBUSvoltage', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='batteryvoltage', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='temperature', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='upstype', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='utilityfail', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='batterylow', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='bypassactive', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='upsfailed', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='epo', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='testinprogress', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='shutdownactive', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='battery_silence', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='battery_test_failed', dependsfrom=['inputvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='battery_test_ok', dependsfrom=['inputvoltage'], timeout=inf),

        # query with b'QFS\r'
        DeviceBackend.VariableInfo(name='lastfault.type', timeout=1.0),
        DeviceBackend.VariableInfo(name='lastfault.inputvoltage', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.inputfrequency', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.outputvoltage', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.outputfrequency', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.outputloadpercentage', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.outputcurrent', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.positiveBUSvoltage', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.negativeBUSvoltage', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.batteryvoltage', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.temperature', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.dctodc_on', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.pfc_on', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.inverter_on', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.inputrelay_on', dependsfrom=['lastfault.type'], timeout=inf),
        DeviceBackend.VariableInfo(name='lastfault.outputrelay_on', dependsfrom=['lastfault.type'], timeout=inf),

        # query with b'QWS\r'
        DeviceBackend.VariableInfo(name='warning.batteryopen', timeout=1.0),
        DeviceBackend.VariableInfo(name='warning.batteryovercharge', dependsfrom=['warning.batteryopen'], timeout=inf),
        DeviceBackend.VariableInfo(name='warning.batterylow', dependsfrom=['warning.batteryopen'], timeout=inf),
        DeviceBackend.VariableInfo(name='warning.overload', dependsfrom=['warning.batteryopen'], timeout=inf),
        DeviceBackend.VariableInfo(name='warning.epo', dependsfrom=['warning.batteryopen'], timeout=inf),
        DeviceBackend.VariableInfo(name='warning.overtemperature', dependsfrom=['warning.batteryopen'], timeout=inf),
        DeviceBackend.VariableInfo(name='warning.chargerfail', dependsfrom=['warning.batteryopen'], timeout=inf),

        # query with b'QMOD\r'
        DeviceBackend.VariableInfo(name='upsmode', timeout=1.0),

        # query with b'QRI\r'
        DeviceBackend.VariableInfo(name='ratedvoltage', timeout=inf),
        DeviceBackend.VariableInfo(name='ratedcurrent', dependsfrom=['ratedvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='ratedbatteryvoltage', dependsfrom=['ratedvoltage'], timeout=inf),
        DeviceBackend.VariableInfo(name='ratedfrequency', dependsfrom=['ratedvoltage'], timeout=inf),

        # query with b'QBYV\r'
        DeviceBackend.VariableInfo(name='bypassvoltage.high', timeout=1.0),
        DeviceBackend.VariableInfo(name='bypassvoltage.low', dependsfrom=['bypassvoltage.high'], timeout=1.0),

        # query with b'QBYF\r'
        DeviceBackend.VariableInfo(name='bypassfrequency.high', timeout=1.0),
        DeviceBackend.VariableInfo(name='bypassfrequency.low', dependsfrom=['bypassfrequency.high'],
                                   timeout=1.0),

        # query with b'QFLAG\r'
        DeviceBackend.VariableInfo(name='flag.bypassmodealarm', timeout=1.0),
        DeviceBackend.VariableInfo(name='flag.batterymodealarm', dependsfrom=['flag.bypassmodealarm'], timeout=inf),
        DeviceBackend.VariableInfo(name='flag.autostartenabled', dependsfrom=['flag.bypassmodealarm'], timeout=inf),
        DeviceBackend.VariableInfo(name='flag.bypassenabled', dependsfrom=['flag.bypassmodealarm'], timeout=inf),
        DeviceBackend.VariableInfo(name='flag.warningalarm', dependsfrom=['flag.bypassmodealarm'], timeout=inf),
        DeviceBackend.VariableInfo(name='flag.batteryprotectenabled', dependsfrom=['flag.bypassmodealarm'],
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='flag.convertermodeenabled', dependsfrom=['flag.bypassmodealarm'], timeout=inf),
        DeviceBackend.VariableInfo(name='flag.batteryopenstatuscheckenabled', dependsfrom=['flag.bypassmodealarm'],
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='flag.bypassforbiddingenabled', dependsfrom=['flag.bypassmodealarm'],
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='flag.batterylowprotectenabled', dependsfrom=['flag.bypassmodealarm'],
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='flag.invertershortclearenabled', dependsfrom=['flag.bypassmodealarm'],
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='flag.hotstantbymaster', dependsfrom=['flag.bypassmodealarm'], timeout=inf),

        # query with b'QFLAG2\r'
        DeviceBackend.VariableInfo(name='flag.thdisetting', timeout=1.0),
        DeviceBackend.VariableInfo(name='flag.standardmodelsetting', dependsfrom=['flag.thdisetting'], timeout=inf),
        DeviceBackend.VariableInfo(name='flag.eepromversion', dependsfrom=['flag.thdisetting'], timeout=inf),
        DeviceBackend.VariableInfo(name='flag.maincapacityovertempcounter', dependsfrom=['flag.thdisetting'],
                                   timeout=inf),

        # query with b'QVFW\r'
        DeviceBackend.VariableInfo(name='firmwareversion', timeout=inf),

        # query with b'QID\r'
        DeviceBackend.VariableInfo(name='hardwareversion', timeout=inf),

        # query with b'QBV\r'
        DeviceBackend.VariableInfo(name='batteryvoltage_2', timeout=1.0),
        # is this equal to the value read by b'QGS\r'?
        DeviceBackend.VariableInfo(name='batterycount_2', dependsfrom=['batteryvoltage_2'], timeout=inf),
        DeviceBackend.VariableInfo(name='batterygroupcount', dependsfrom=['batteryvoltage_2'], timeout=inf),
        DeviceBackend.VariableInfo(name='batterycapacity', dependsfrom=['batteryvoltage_2'], timeout=inf),
        DeviceBackend.VariableInfo(name='batteryremaintime', dependsfrom=['batteryvoltage_2'], timeout=inf),

        # query with b'QLDL\r'
        DeviceBackend.VariableInfo(name='loadlevel_wattpercent', timeout=1.0),
        DeviceBackend.VariableInfo(name='loadlevel_vapercent', dependsfrom=['loadlevel_wattpercent'], timeout=inf),

        # query with b'QTPR\r'
        DeviceBackend.VariableInfo(name='temperature.pfc', timeout=1.0),
        DeviceBackend.VariableInfo(name='temperature.ambient', dependsfrom=['temperature.pfc'], timeout=inf),
        DeviceBackend.VariableInfo(name='temperature.charger', dependsfrom=['temperature.pfc'], timeout=inf),

    ]

    def _query(self, variablename: str):
        if variablename == 'protocolID':
            self.enqueueHardwareMessage(b'QPI\r')
        elif variablename == 'modelname':
            self.enqueueHardwareMessage(b'QMD\r')
        elif variablename == 'inputvoltage':
            self.enqueueHardwareMessage(b'QGS\r')
        elif variablename == 'lastfault.type':
            self.enqueueHardwareMessage(b'QFS\r')
        elif variablename == 'warning.batteryopen':
            self.enqueueHardwareMessage(b'QWS\r')
        elif variablename == 'upsmode':
            self.enqueueHardwareMessage(b'QMOD\r')
        elif variablename == 'ratedvoltage':
            self.enqueueHardwareMessage(b'QRI\r')
        elif variablename == 'bypassvoltage.high':
            self.enqueueHardwareMessage(b'QBYV\r')
        elif variablename == 'bypassfrequency.high':
            self.enqueueHardwareMessage(b'QBYF\r')
        elif variablename == 'flag.bypassmodealarm':
            self.enqueueHardwareMessage(b'QFLAG\r')
        elif variablename == 'flag.thdisetting':
            self.enqueueHardwareMessage(b'QFLAG2\r')
        elif variablename == 'firmwareversion':
            self.enqueueHardwareMessage(b'QVFW\r')
        elif variablename == 'hardwareversion':
            self.enqueueHardwareMessage(b'QID\r')
        elif variablename == 'batteryvoltage_2':
            self.enqueueHardwareMessage(b'QBV\r')
        elif variablename == 'loadlevel_wattpercent':
            self.enqueueHardwareMessage(b'QLDL\r')
        elif variablename == 'temperature.pfc':
            self.enqueueHardwareMessage(b'QTPR\r')
        else:
            self.error(f'Unknown variable: {variablename}')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        msgs = message.split(b'\r')
        return msgs[:-1], msgs[-1]

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        #        self.debug(f'Interpreting message: {message.decode("ascii")} (sent: {sentmessage.decode("ascii")[:-1]})')
        if (m := re.match(br'\(PI\s+(?P<protocolID>\d{2})', message)) and (sentmessage == b'QPI\r'):
            self.updateVariable('protocolid', int(m['protocolid']))
        elif (m := re.match(
                br'\((?P<modelname>(\w|#){15}) '
                br'(?P<ratedVA>(\d|#){7}) '
                br'(?P<powerfactor>\d{2}) '
                br'(?P<inputphasecount>\d)/(?P<outputphasecount>\d) '
                br'(?P<nominalinputvoltage>\d{3}) '
                br'(?P<nominaloutputvoltage>\d{3}) '
                br'(?P<batterycount>\d{2}) '
                br'(?P<nominalbatteryvoltage>\d\d\.\d)', message)) and (sentmessage == b'QMD\r'):
            self.updateVariable('modelname', m['modelname'].decode('utf-8').replace('#', ''))
            self.updateVariable('ratedVA', int(m['ratedVA'].decode('utf-8').replace('#', '')))
            self.updateVariable('powerfactor', int(m['powerfactor']) / 100.)
            self.updateVariable('inputphasecount', int(m['inputphasecount']))
            self.updateVariable('outputphasecount', int(m['outputphasecount']))
            self.updateVariable('nominalinputvoltage', float(m['nominalinputvoltage']))
            self.updateVariable('nominaloutputvoltage', float(m['nominaloutputvoltage']))
            self.updateVariable('batterycount', int(m['batterycount']))
            self.updateVariable('nominalbatteryvoltage', float(m['nominalbatteryvoltage']))
        elif (m := re.match(br'\(((?P<inputvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<inputfrequency>\d{2}\.\d)|(--\.-)) '
                            br'((?P<outputvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<outputfrequency>\d{2}\.\d)|(--\.-)) '
                            br'((?P<outputcurrent>\d{3}\.\d)|(---\.-)) '
                            br'((?P<outputloadpercentage>\d{3})|(---\.-)) '
                            br'((?P<positiveBUSvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<negativeBUSvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<batteryvoltage>\d{3}\.\d)|(---\.-)) '
                            br'---\.- '
                            br'((?P<temperature>\d{3}\.\d)|(---\.-)) '
                            br'(?P<upstype>[01]{2})'
                            br'(?P<utilityfail>[01])'
                            br'(?P<batterylow>[01])'
                            br'(?P<bypassactive>[01])'
                            br'(?P<upsfailed>[01])'
                            br'(?P<epo>[01])'
                            br'(?P<testinprogress>[01])'
                            br'(?P<shutdownactive>[01])'
                            br'(?P<battery_silence>[01])'
                            br'(?P<battery_test_failed>[01])'
                            br'(?P<battery_test_ok>[01])', message)) and (sentmessage == b'QGS\r'):
            for floatparam in ['inputvoltage', 'inputfrequency', 'outputvoltage', 'outputfrequency',
                               'outputcurrent', 'outputloadpercentage', 'positiveBUSvoltage',
                               'negativeBUSvoltage', 'batteryvoltage', 'temperature']:
                self.updateVariable(floatparam, float(m[floatparam]) if floatparam in m else None)
            for boolparam in ['utilityfail', 'batterylow', 'bypassactive', 'upsfailed', 'epo', 'testinprogress',
                              'shutdownactive', 'battery_silence', 'battery_test_failed', 'battery_test_ok']:
                self.updateVariable(boolparam, bool(int(m[boolparam])))
            if m['upstype'] == b'00':
                self.updateVariable('upstype', 'standby')
            elif m['upstype'] == b'01':
                self.updateVariable('upstype', 'line-interactive')
            elif m['upstype'] == b'10':
                self.updateVariable('upstype', 'on-line')
            else:
                self.updateVariable('upstype', 'unknown')
        elif (m := re.match(br'\(OK', message)) and (sentmessage == b'QFS\r'):
            self.updateVariable('', m[''])
            for varname in ['lastfault.type', 'lastfault.inputvoltage', 'lastfault.inputfrequency',
                            'lastfault.outputvoltage', 'lastfault.outputfrequency', 'lastfault.outputloadpercentage',
                            'lastfault.outputcurrent', 'lastfault.positiveBUSvoltage', 'lastfault.negativeBUSvoltage',
                            'lastfault.batteryvoltage', 'lastfault.temperature', 'lastfault.dctodc_on',
                            'lastfault.pfc_on', 'lastfault.inverter_on', 'lastfault.inputrelay_on',
                            'lastfault.outputrelay_on']:
                self.updateVariable(varname, None)
        elif (m := re.match(br'\((?P<type>[0-9a-f]{2}) '
                            br'((?P<inputvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<inputfrequency>\d{2}\.\d)|(--\.-)) '
                            br'((?P<outputvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<outputfrequency>\d{2}\.\d)|(--\.-)) '
                            br'((?P<outputloadpercentage>\d{3})|(---)) '
                            br'((?P<outputcurrent>\d{3}\.\d)|(---\.-)) '
                            br'((?P<positiveBUSvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<negativeBUSvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<batteryvoltage>\d{3}\.\d)|(---\.-)) '
                            br'((?P<temperature>\d{3}\.\d)|(---\.-)) '
                            br'(?P<dctodc_on>[01]) '
                            br'(?P<pfc_on>[01]) '
                            br'(?P<inverter_on>[01]) '
                            br'(?P<inputrelay_on>[01]) '
                            br'(?P<outputrelay_on>[01])',
                            message)) and (sentmessage == b'QFS\r'):
            if m['type'] == b'01':
                self.updateVariable('lastfault.type', 'Bus start fail')
            elif m['type'] == b'02':
                self.updateVariable('lastfault.type', 'Bus overvoltage')
            elif m['type'] == b'03':
                self.updateVariable('lastfault.type', 'Bus undervoltage')
            elif m['type'] == b'04':
                self.updateVariable('lastfault.type', 'Bus voltage imbalance')
            elif m['type'] == b'11':
                self.updateVariable('lastfault.type', 'Inverter soft fail')
            elif m['type'] == b'12':
                self.updateVariable('lastfault.type', 'Inverter overvoltage')
            elif m['type'] == b'13':
                self.updateVariable('lastfault.type', 'Inverter undervoltage')
            elif m['type'] == b'14':
                self.updateVariable('lastfault.type', 'Inverter output short circuited')
            elif m['type'] == b'21':
                self.updateVariable('lastfault.type', 'Battery short circuit fault')
            elif m['type'] == b'41':
                self.updateVariable('lastfault.type', 'Overtemperature')
            elif m['type'] == b'43':
                self.updateVariable('lastfault.type', 'Overload')
            elif m['type'] == b'46':
                self.updateVariable('lastfault.type', 'Battery count error')
            for floatparameter in ['inputvoltage', 'inputfrequency', 'outputvoltage', 'outputfrequency',
                                   'outputloadpercentage', 'outputcurrent', 'positiveBUSvoltage', 'negativeBUSvoltage',
                                   'batteryvoltage', 'temperature']:
                self.updateVariable(f'lastfault.{floatparameter}',
                                    float(m[floatparameter]) if floatparameter in m else None)
            for boolparameter in ['dctodc_on', 'pfc_on', 'inverter_on', 'inputrelay_on', 'outputrealy_on']:
                self.updateVariable(f'lastfault.{boolparameter}', bool(int(m[boolparameter])))
        elif (m := re.match(br'\((?P<status>[01]{64})', message)) and (sentmessage == b'QWS\r'):
            self.updateVariable('warning.batteryopen', m['status'][0:1] == b'1')
            self.updateVariable('warning.batteryovercharge', m['status'][6:7] == b'1')
            self.updateVariable('warning.batterylow', m['status'][7:8] == b'1')
            self.updateVariable('warning.overload', m['status'][8:9] == b'1')
            self.updateVariable('warning.epo', m['status'][10:11] == b'1')
            self.updateVariable('warning.overtemperature', m['status'][12:13] == b'1')
            self.updateVariable('warning.chargerfail', m['status'][13:14] == b'1')
        elif (m := re.match(br'\((?P<upsmode>[PSYLBTFECD])', message)) and (sentmessage == b'QMOD\r'):
            mode = \
            {'P': 'Power on', 'S': 'Standby', 'Y': 'Bypass', 'L': 'Line', 'B': 'Battery', 'T': 'Test', 'F': 'Fault',
             'E': 'HE/ECO', 'C': 'Converter', 'D': 'Shutdown'}[m['upsmode'].decode('ascii')]
            self.updateVariable('upsmode', mode)
            self.updateVariable('__status__', mode)
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
        elif (m := re.match(br'\(', message)) and (sentmessage == b'Q\r'):
            self.updateVariable('', m[''])
