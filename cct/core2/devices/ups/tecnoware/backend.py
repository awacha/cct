import re
from math import inf
from typing import Tuple, List, Optional, Union, Sequence, Any, Dict, Final

from ...device.backend import DeviceBackend


def re_optional_float(name: str, nintdigits: int = 3, ndecimals: int = 0, bytes: bool = True) -> Union[bytes, str]:
    """Produce a regular expression """
    if ndecimals > 0:
        regex = fr'(?:(?P<{name}>\d{{{nintdigits}}}\.\d{{{ndecimals}}})|(?:-{{{nintdigits}}}\.-{{{ndecimals}}}))'
    else:
        regex = fr'(?:(?P<{name}>\d{{{nintdigits}}})|(?:-{{{nintdigits}}}))'
    if bytes:
        return regex.encode('utf-8')
    else:
        return regex


def safe_float(x: Union[bytes, str, None]) -> Optional[float]:
    return float(x) if x is not None else None


def safe_int(x: Union[bytes, str, None]) -> Optional[int]:
    return int(x) if x is not None else None


class TecnowareEvoDSPPlusBackend(DeviceBackend):
    class Status(DeviceBackend.Status):
        Power_on = 'Power on'
        Standby = 'Standby'
        Bypass = 'Bypass'
        Line = 'Line'
        Battery = 'Battery'
        Testing = 'Testing'
        Fault = 'Fault'
        Eco = 'HE/ECO'
        Converter = 'Converter'
        Shutdown = 'Shutdown'

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
        DeviceBackend.VariableInfo(name='flag.hotstandbymaster', dependsfrom=['flag.bypassmodealarm'], timeout=inf),

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

    re_protocolid: Final[re.Pattern] = re.compile(br'\(PI\s*(?P<protocolID>\d{2})')
    re_modelinfo: Final[re.Pattern] = re.compile(
        br'\((?P<modelname>(\w|#){15}) '
        br'(?P<ratedVA>(\d|#){7}) '
        br'(?P<powerfactor>\d{2}) '
        br'(?P<inputphasecount>\d)/(?P<outputphasecount>\d) '
        br'(?P<nominalinputvoltage>\d{3}) '
        br'(?P<nominaloutputvoltage>\d{3}) '
        br'(?P<batterycount>\d{2}) '
        br'(?P<nominalbatteryvoltage>\d\d\.\d)')
    re_generalinfo: Final[re.Pattern] = re.compile(
        br'\(' + re_optional_float('inputvoltage', 3, 1) + b' ' +
        re_optional_float('inputfrequency', 2, 1) + b' ' +
        re_optional_float('outputvoltage', 3, 1) + b' ' +
        re_optional_float('outputfrequency', 2, 1) + b' ' +
        re_optional_float('outputcurrent', 3, 1) + b' ' +
        re_optional_float('outputloadpercentage', 3, 0) + b' ' +
        re_optional_float('positiveBUSvoltage', 3, 1) + b' ' +
        re_optional_float('negativeBUSvoltage', 3, 1) + b' ' +
        re_optional_float('batteryvoltage', 3, 1) + b' ' +
        br'---\.- ' +
        re_optional_float('temperature', 3, 1) + b' ' +
        br'(?P<upstype>[01]{2})' +
        br'(?P<utilityfail>[01])' +
        br'(?P<batterylow>[01])' +
        br'(?P<bypassactive>[01])' +
        br'(?P<upsfailed>[01])' +
        br'(?P<epo>[01])' +
        br'(?P<testinprogress>[01])' +
        br'(?P<shutdownactive>[01])' +
        br'(?P<battery_silence>[01])' +
        br'(?P<battery_test_failed>[01])' +
        br'(?P<battery_test_ok>[01])'
    )
    re_ok: Final[re.Pattern] = re.compile(br'\(OK')
    re_faultstatus: Final[re.Pattern] = re.compile(
        br'\((?P<type>[0-9a-f]{2}) ' +
        re_optional_float('inputvoltage', 3, 1) + b' ' +
        re_optional_float('inputfrequency', 2, 1) + b' ' +
        re_optional_float('outputvoltage', 3, 1) + b' ' +
        re_optional_float('outputfrequency', 2, 1) + b' ' +
        re_optional_float('outputloadpercentage', 3, 0) + b' ' +
        re_optional_float('outputcurrent', 3, 1) + b' ' +
        re_optional_float('positiveBUSvoltage', 3, 1) + b' ' +
        re_optional_float('negativeBUSvoltage', 3, 1) + b' ' +
        re_optional_float('batteryvoltage', 3, 1) + b' ' +
        re_optional_float('temperature', 3, 1) + b' ' +
        br'(?P<dctodc_on>[01])' +
        br'(?P<pfc_on>[01])' +
        br'(?P<inverter_on>[01])' +
        br'(?P<inputrelay_on>[01])' +
        br'(?P<outputrelay_on>[01])')
    re_warningstatus: Final[re.Pattern] = re.compile(br'\((?P<status>[01]{64})')
    re_upsmode: Final[re.Pattern] = re.compile(br'\((?P<upsmode>[PSYLBTFECD])')
    re_ratings: Final[re.Pattern] = re.compile(
        br'\(' +
        re_optional_float('ratedvoltage', 3, 1) + b' ' +
        re_optional_float('ratedcurrent', 3, 0) + b' ' +
        re_optional_float('ratedbatteryvoltage', 3, 1) + b' ' +
        re_optional_float('ratedfrequency', 2, 1))
    re_bypassvoltage: Final[re.Pattern] = re.compile(
        br'\(' +
        re_optional_float('bypassvoltage_high', 3, 0) + b' ' +
        re_optional_float('bypassvoltage_low', 3, 0))
    re_bypassfrequency: Final[re.Pattern] = re.compile(
        br'\(' +
        re_optional_float('bypassfrequency_high', 2, 1) + b' ' +
        re_optional_float('bypassfrequency_low', 2, 1))
    re_flags: Final[re.Pattern] = re.compile(
        br'\((?:E(?P<enabled>[pbroasvdftim]*))?(?:D(?P<disabled>[pbroasvdftim]*))?')
    re_flags2: Final[re.Pattern] = re.compile(
        br'\((?P<thdisetting>\d)(?P<standardmodelsetting>\d)'
        br'(?P<eepromversion>\d)(?P<maincapacityovertempcounter>\d)')
    re_verfw: Final[re.Pattern] = re.compile(br'\(VERFW:(?P<firmwareversion>.*)')
    re_hardwareversion: Final[re.Pattern] = re.compile(br'\((?P<hardwareversion>[a-zA-Z0-9]{14})')
    re_batteryinfo: Final[re.Pattern] = re.compile(
        br'\(' +
        re_optional_float('batteryvoltage_2', 3, 1) + b' ' +
        re_optional_float('batterycount_2', 2, 0) + b' ' +
        re_optional_float('batterygroupcount', 2, 0) + b' ' +
        re_optional_float('batterycapacity', 3, 0) + b' ' +
        br'(?:(?P<batteryremaintime>\d{3}|\d{5})|(-+))')
    re_loadlevel: Final[re.Pattern] = re.compile(
        br'\(' +
        re_optional_float('loadlevel_wattpercent', 3, 0) + b' ' +
        re_optional_float('loadlevel_vapercent', 3, 0))
    re_temperature: Final[re.Pattern] = re.compile(
        br'\(' +
        re_optional_float('temperature_pfc', 3, 1) + b' ' +
        re_optional_float('temperature_ambient', 3, 1) + b' ' +
        re_optional_float('temperature_charger', 3, 1) + b' ' + b'---\.-')
    re_acknowledgement: Final[re.Pattern] = re.compile(br'\((?P<ack>ACK|NAK)')
    _flagchars: Final[Dict[str, str]] = dict([
        ('bypassmodealarm', 'p'),
        ('batterymodealarm', 'b'),
        ('autostartenabled', 'r'),
        ('bypassenabled', 'o'),
        ('warningalarm', 'a'),
        ('batteryprotectenabled', 's'),
        ('convertermodeenabled', 'v'),
        ('batteryopenstatuscheckenabled', 'd'),
        ('bypassforbiddingenabled', 'f'),
        ('batterylowprotectenabled', 't'),
        ('invertershortclearenabled', 'i'),
        ('hotstandbymaster', 'm'),
    ])

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
        if (m := self.re_protocolid.match(message)) and (sentmessage == b'QPI\r'):
            self.updateVariable('protocolID', int(m['protocolID']))
        elif (m := self.re_modelinfo.match(message)) and (sentmessage == b'QMD\r'):
            self.updateVariable('modelname', m['modelname'].decode('utf-8').replace('#', ''))
            self.updateVariable('ratedVA', int(m['ratedVA'].decode('utf-8').replace('#', '')))
            self.updateVariable('powerfactor', int(m['powerfactor']) / 100.)
            self.updateVariable('inputphasecount', int(m['inputphasecount']))
            self.updateVariable('outputphasecount', int(m['outputphasecount']))
            self.updateVariable('nominalinputvoltage', float(m['nominalinputvoltage']))
            self.updateVariable('nominaloutputvoltage', float(m['nominaloutputvoltage']))
            self.updateVariable('batterycount', int(m['batterycount']))
            self.updateVariable('nominalbatteryvoltage', float(m['nominalbatteryvoltage']))
        elif (m := self.re_generalinfo.match(message)) and (sentmessage == b'QGS\r'):
            for floatparam in ['inputvoltage', 'inputfrequency', 'outputvoltage', 'outputfrequency',
                               'outputcurrent', 'outputloadpercentage', 'positiveBUSvoltage',
                               'negativeBUSvoltage', 'batteryvoltage', 'temperature']:
                self.updateVariable(floatparam, safe_float(m[floatparam]))
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
        elif (m := self.re_ok.match(message)) and (sentmessage == b'QFS\r'):
            for varname in ['lastfault.type', 'lastfault.inputvoltage', 'lastfault.inputfrequency',
                            'lastfault.outputvoltage', 'lastfault.outputfrequency', 'lastfault.outputloadpercentage',
                            'lastfault.outputcurrent', 'lastfault.positiveBUSvoltage', 'lastfault.negativeBUSvoltage',
                            'lastfault.batteryvoltage', 'lastfault.temperature', 'lastfault.dctodc_on',
                            'lastfault.pfc_on', 'lastfault.inverter_on', 'lastfault.inputrelay_on',
                            'lastfault.outputrelay_on']:
                self.updateVariable(varname, None)
        elif (m := self.re_faultstatus.match(message)) and (sentmessage == b'QFS\r'):
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
                                    safe_float(m[floatparameter]))
            for boolparameter in ['dctodc_on', 'pfc_on', 'inverter_on', 'inputrelay_on', 'outputrelay_on']:
                self.updateVariable(f'lastfault.{boolparameter}', bool(int(m[boolparameter])))
        elif (m := self.re_warningstatus.match(message)) and (sentmessage == b'QWS\r'):
            self.updateVariable('warning.batteryopen', m['status'][0:1] == b'1')
            self.updateVariable('warning.batteryovercharge', m['status'][6:7] == b'1')
            self.updateVariable('warning.batterylow', m['status'][7:8] == b'1')
            self.updateVariable('warning.overload', m['status'][8:9] == b'1')
            self.updateVariable('warning.epo', m['status'][10:11] == b'1')
            self.updateVariable('warning.overtemperature', m['status'][12:13] == b'1')
            self.updateVariable('warning.chargerfail', m['status'][13:14] == b'1')
        elif (m := self.re_upsmode.match(message)) and (sentmessage == b'QMOD\r'):
            mode = {
                'P': 'Power on', 'S': 'Standby', 'Y': 'Bypass', 'L': 'Line', 'B': 'Battery', 'T': 'Testing',
                'F': 'Fault', 'E': 'HE/ECO', 'C': 'Converter', 'D': 'Shutdown'}[m['upsmode'].decode('ascii')]
            self.updateVariable('upsmode', mode)
            self.updateVariable('__status__', mode)
        elif (m := self.re_ratings.match(message)) and (sentmessage == b'QRI\r'):
            for floatparameter in ['ratedvoltage', 'ratedcurrent', 'ratedbatteryvoltage', 'ratedfrequency']:
                self.updateVariable(floatparameter, safe_float(m[floatparameter]))
        elif (m := self.re_bypassvoltage.match(message)) and (sentmessage == b'QBYV\r'):
            self.updateVariable('bypassvoltage.high', safe_float(m['bypassvoltage_high']))
            self.updateVariable('bypassvoltage.low', safe_float(m['bypassvoltage_low']))
        elif (m := self.re_bypassfrequency.match(message)) and (sentmessage == b'QBYF\r'):
            self.updateVariable('bypassfrequency.high', safe_float(m['bypassfrequency_high']))
            self.updateVariable('bypassfrequency.low', safe_float(m['bypassfrequency_low']))
        elif (m := self.re_flags.match(message)) and (sentmessage == b'QFLAG\r'):
            enabled = m['enabled'].decode('ascii') if m['enabled'] is not None else ''
            disabled = m['disabled'].decode('ascii') if m['disabled'] is not None else ''
            for flagname, short in self._flagchars.items():
                if short in enabled:
                    self.updateVariable(f'flag.{flagname}', True)
                elif short in disabled:
                    self.updateVariable(f'flag.{flagname}', False)
                else:
                    raise RuntimeError(f'Flag {flagname} (short name {short}) neither enabled nor disabled')
        elif (m := self.re_flags2.match(message)) and (sentmessage == b'QFLAG2\r'):
            for group in m.groupdict():
                self.updateVariable('flag.' + group, int(m[group]))
        elif (m := self.re_verfw.match(message)) and (sentmessage == b'QVFW\r'):
            self.updateVariable('firmwareversion', m['firmwareversion'].decode('utf-8').strip())
        elif (m := self.re_hardwareversion.match(message)) and (sentmessage == b'QID\r'):
            self.updateVariable('hardwareversion', m['hardwareversion'].decode('utf-8').strip())
        elif (m := self.re_batteryinfo.match(message)) and (sentmessage == b'QBV\r'):
            self.updateVariable('batteryvoltage_2', safe_float(m['batteryvoltage_2']))
            self.updateVariable('batterycount_2', safe_int(m['batterycount_2']))
            self.updateVariable('batterygroupcount', safe_int(m['batterygroupcount']))
            self.updateVariable('batterycapacity', safe_int(m['batterycapacity']))
            self.updateVariable('batteryremaintime', safe_int(m['batteryremaintime']))
        elif (m := self.re_loadlevel.match(message)) and (sentmessage == b'QLDL\r'):
            self.updateVariable('loadlevel_wattpercent', safe_float(m['loadlevel_wattpercent']))
            self.updateVariable('loadlevel_vapercent', safe_float(m['loadlevel_vapercent']))
            self.updateVariable('__auxstatus__', f'{self["loadlevel_wattpercent"]:.0f}%')
        elif (m := self.re_temperature.match(message)) and (sentmessage == b'QTPR\r'):
            self.updateVariable('temperature.pfc', safe_float(m['temperature_pfc']))
            self.updateVariable('temperature.ambient', safe_float(m['temperature_ambient']))
            self.updateVariable('temperature.charger', safe_float(m['temperature_charger']))
        elif (m := self.re_acknowledgement.match(message)) and (sentmessage.startswith(b'PE') or sentmessage.startswith(b'PD')):
            self.commandFinished('setflag' if sentmessage.startswith(b'PE') else 'clearflag', m['ack'].decode('utf-8'))
        else:
            raise ValueError(f'Invalid reply for sent message *{sentmessage}*: *{message}*')

    def issueCommand(self, name: str, args: Sequence[Any]):
        if name in ['setflag', 'clearflag']:
            flagname = args[0]
            if flagname not in self._flagchars:
                self.commandError(name, f'Unknown flag {flagname}')
            else:
                self.enqueueHardwareMessage(
                    f'P{"E" if name == "setflag" else "D"}{self._flagchars[flagname]}\r'.upper().encode('ascii'))
        else:
            self.commandError(name, f'Unknown command {name}')