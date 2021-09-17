from math import inf
from typing import Sequence, Any, Tuple, List

from ...device.backend import DeviceBackend


class Keen800Backend(DeviceBackend):
    class Status(DeviceBackend.Status):
        GridPower = 'grid'
        BatteryPower = 'battery'

    varinfo = [
        DeviceBackend.VariableInfo(name='inputvoltage', dependsfrom=[], urgent=False, timeout=1.0),
        DeviceBackend.VariableInfo(name='inputfaultvoltage', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='outputvoltage', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='outputcurrentpercentage', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='inputfrequency', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='batteryvoltage', dependsfrom=['inputvoltage'], urgent=False,
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='temperature', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='utilityfail', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='batterylow', dependsfrom=['inputvoltage'], urgent=False,
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='bypassactive', dependsfrom=['inputvoltage'], urgent=False,
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='upsfailed', dependsfrom=['inputvoltage'], urgent=False,
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='standbyups', dependsfrom=['inputvoltage'], urgent=False,
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='testinprogress', dependsfrom=['inputvoltage'], urgent=False,
                                   timeout=inf),
        DeviceBackend.VariableInfo(name='shutdownactive', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='beeperon', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ratedvoltage', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ratedcurrent', dependsfrom=['ratedvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ratedbatteryvoltage', dependsfrom=['ratedvoltage'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='ratedfrequency', dependsfrom=['ratedfrequency'], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='statusbits', dependsfrom=['inputvoltage'], urgent=False, timeout=inf),

    ]

    def _query(self, variablename: str):
        if variablename == 'inputvoltage':
            self.enqueueHardwareMessage(b'Q1\r')
        elif variablename == 'ratedvoltage':
            self.enqueueHardwareMessage(b'F\r')
        else:
            self.error(f'Unknown variable: {variablename}')

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        msgs = message.split(b'\r')
        return msgs[:-1], msgs[-1]

    def interpretMessage(self, message: bytes, sentmessage: bytes):
#        self.debug(f'Interpreting message: {message.decode("ascii")} (sent: {sentmessage.decode("ascii")[:-1]})')
        if message.startswith(b'(') and sentmessage == b'Q1\r':
            inputvoltage, inputfaultvoltage, outputvoltage, outputcurrentpercentage, inputfrequency, batteryvoltage, temperature, statusbits = message[1:].decode('ascii').split()
            self.updateVariable('statusbits', statusbits)
            self.updateVariable('inputvoltage', float(inputvoltage))
            self.updateVariable('inputfaultvoltage', float(inputfaultvoltage))
            self.updateVariable('outputvoltage', float(outputvoltage))
            self.updateVariable('outputcurrentpercentage', float(outputcurrentpercentage))
            self.updateVariable('inputfrequency', float(inputfrequency))
            self.updateVariable('batteryvoltage', float(batteryvoltage))
            self.updateVariable('temperature', float(temperature))
            self.updateVariable('utilityfail', statusbits[0]=='1')
            self.updateVariable('__status__', self.Status.BatteryPower if statusbits[0]=='1' else self.Status.GridPower)
            self.updateVariable('__auxstatus__', f'{float(outputcurrentpercentage):.0f}% usage')
            self.updateVariable('batterylow', statusbits[1]=='1')
            self.updateVariable('bypassactive', statusbits[2]=='1')
            self.updateVariable('upsfailed', statusbits[3]=='1')
            self.updateVariable('standbyups', statusbits[4]=='1')
            self.updateVariable('testinprogress', statusbits[5]=='1')
            self.updateVariable('shutdownactive', statusbits[6]=='1')
            self.updateVariable('beeperon', statusbits[7]=='1')
        elif message.startswith(b'#') and sentmessage == b'F\r':
            ratedvoltage, ratedcurrent, ratedbatteryvoltage, ratedfrequency = message[1:].decode('ascii').split()
            self.updateVariable('ratedvoltage', float(ratedvoltage))
            self.updateVariable('ratedcurrent', float(ratedcurrent))
            self.updateVariable('ratedbatteryvoltage', float(ratedbatteryvoltage))
            self.updateVariable('ratedfrequency', float(ratedfrequency))
