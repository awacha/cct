import itertools
import re
import time
from math import inf
from multiprocessing import Queue
from typing import Sequence, Any, Tuple, List, Dict, Optional

from .conversion import UnitConverter
from .tmcl import TMCLUnpack, TMCLPack, TMCLError, AxisParameters, Instructions
from ...device.backend import DeviceBackend


class MotionData:
    axis: int
    cmdenqueuetime: Optional[float] = None
    cmdacktime: Optional[float] = None
    nonzerospeedseenat: Optional[float] = None
    targetpositionreachedwasfalseat: Optional[float] = None
    originaltimeouts: Dict[str, float]
    targetposition: Optional[float] = None
    direction: Optional[str]  # "left" or "right"
    stopcmdenquetime: Optional[float] = None
    stopcmdacktime: Optional[float] = None

    def __init__(self, axis: int):
        self.originaltimeouts = {}
        self.axis = axis


class TrinamicMotorControllerBackend(DeviceBackend):
    class Status(DeviceBackend.Status):
        Moving = 'Moving'

    Naxes: int
    topRMScurrent: float
    max_microsteps: int
    clock_frequency: int
    full_step_size: float
    positionfile: str

    per_controller_variables = ['firmwareversion']
    position_variables = ['targetposition', 'actualposition']
    speed_variables = ['targetspeed', 'actualspeed', 'maxspeed']
    acceleration_variables = ['actualacceleration', 'maxacceleration']
    current_variables = ['maxcurrent', 'standbycurrent']
    converters: List[UnitConverter]
    motionstatus: Dict[int, MotionData]
    motion_query_timeout: float = 0.1

    varinfo = [
        # version of the firmware running in the TMCM controller. Query only once, at the beginning.
        DeviceBackend.VariableInfo(name='firmwareversion', dependsfrom=[], urgent=False, timeout=inf),
        # the following variables are per-axis ones: they have
        DeviceBackend.VariableInfo(name='targetpositionreached', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='targetposition', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='actualposition', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='targetspeed', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='actualspeed', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='rightswitchstatus', dependsfrom=[], urgent=False, timeout=1.0),
        DeviceBackend.VariableInfo(name='leftswitchstatus', dependsfrom=[], urgent=False, timeout=1.0),
        DeviceBackend.VariableInfo(name='actualacceleration', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='load', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='drivererror', dependsfrom=[], urgent=False, timeout=1.0),
        DeviceBackend.VariableInfo(name='rampmode', dependsfrom=[], urgent=False, timeout=inf),
        # the following variables are not changeable from CCT and are not expected to be changed externally.
        DeviceBackend.VariableInfo(name='pulsedivisor', dependsfrom=[], urgent=True, timeout=inf),
        DeviceBackend.VariableInfo(name='rampdivisor', dependsfrom=[], urgent=True, timeout=inf),
        DeviceBackend.VariableInfo(name='microstepresolution', dependsfrom=[], urgent=True, timeout=inf),
        DeviceBackend.VariableInfo(name='maxcurrent', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='standbycurrent', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='rightswitchenable', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='leftswitchenable', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='freewheelingdelay', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='maxspeed', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='maxacceleration', dependsfrom=[], urgent=False, timeout=inf),
        # These are special: not from the controller but read and written to a file.
        DeviceBackend.VariableInfo(name='softleft', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='softright', dependsfrom=[], urgent=False, timeout=inf),
        # this is also a special, per-axis variable, set by the program.
        DeviceBackend.VariableInfo(name='moving', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='movestartposition', dependsfrom=[], urgent=False, timeout=inf),
        DeviceBackend.VariableInfo(name='lastmovewassuccessful', dependsfrom=[], urgent=False, timeout=inf),
    ]

    def __init__(self, inqueue: Queue, outqueue: Queue, host: str, port: int, **kwargs):
        # Extend the `varinfo` structure: some variables are per-axis.
        original_varinfo = self.varinfo
        self.varinfo = []
        for vi in [v for v in original_varinfo]:
            assert isinstance(vi, DeviceBackend.VariableInfo)
            if vi.name in self.per_controller_variables:
                # do not multiply, this is a per-controller variable
                self.varinfo.append(vi)
            else:
                # per-axis variable, make a copy of this variable for each axis
                for iaxis in range(self.Naxes):
                    self.varinfo.append(
                        DeviceBackend.VariableInfo(
                            name=f'{vi.name}${iaxis}',
                            dependsfrom=[],  # ToDo
                            urgent=vi.urgent,
                            timeout=vi.timeout
                        )
                    )
        # some variables can be expressed in physically relevant units, but the controller reports their "raw" values.
        for varname in [vi.name for vi in self.varinfo]:
            varbasename = varname.split('$')[0]  # for all we know, this could be a per-axis variable
            peraxistag = ('$' + varname.split('$')[1]) if '$' in varname else ''
            if varbasename in (
                    self.current_variables + self.position_variables + self.speed_variables + self.acceleration_variables):
                # add a raw version
                varinfo = [vi for vi in self.varinfo if vi.name == varname][0]
                self.varinfo.append(
                    DeviceBackend.VariableInfo(
                        name=f'{varbasename}:raw{peraxistag}',
                        dependsfrom=varinfo.dependsfrom,
                        urgent=varinfo.urgent,
                        timeout=varinfo.timeout
                    ))
                # make the physical one depend from the raw one.
                varinfo.dependsfrom = [f'{varbasename}:raw{peraxistag}']

        # now we can call __init__() of the parent class, which will create an appropriate `variables` list
        super().__init__(inqueue, outqueue, host, port)
        self.positionfile = kwargs['positionfile']
        self.converters = [
            UnitConverter(self.topRMScurrent, self.full_step_size, self.clock_frequency) for i in
            range(self.Naxes)]
        posinfo = self.readMotorPosFile()
        if len(posinfo) != self.Naxes:
            raise ValueError(f'Number of positions read from file {self.positionfile} ({len(posinfo)} is not the same '
                             f'as the number of axes (${self.Naxes}).')
        self.motionstatus = {}

    def _query(self, variablename: str):
        msg = None
        if variablename in self.per_controller_variables:
            # per-controller variables: only a single copy exists of each
            if variablename == 'firmwareversion':
                msg = TMCLPack(Instructions.GetFirmwareVersion, 1, 0, 0)
            else:
                raise ValueError(f'Unknown variable: {variablename}')
        else:
            # TMCL instruction number #6: GAP (get axis parameter)
            basename, axis = variablename.split('$')
            axis = int(axis)
            if basename == 'targetpositionreached':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.TargetPositionReached, axis, 0)
            elif basename == 'targetposition:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.TargetPosition, axis, 0)
            elif basename == 'actualposition:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.ActualPosition, axis, 0)
            elif basename == 'targetspeed:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.TargetSpeed, axis, 0)
            elif basename == 'actualspeed:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.ActualSpeed, axis, 0)
            elif basename == 'rightswitchstatus':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.RightLimitSwitchStatus, axis, 0)
            elif basename == 'leftswitchstatus':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.LeftLimitSwitchStatus, axis, 0)
            elif basename == 'actualacceleration:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.ActualAcceleration, axis, 0)
            elif basename == 'load':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.ActualLoadValue, axis, 0)
            elif basename == 'drivererror':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.DriverErrorFlags, axis, 0)
            elif basename == 'rampmode':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.RampMode, axis, 0)
            elif basename == 'pulsedivisor':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.PulseDivisor, axis, 0)
            elif basename == 'rampdivisor':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.RampDivisor, axis, 0)
            elif basename == 'microstepresolution':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.MicrostepResolution, axis, 0)
            elif basename == 'maxcurrent:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.AbsoluteMaxCurrent, axis, 0)
            elif basename == 'standbycurrent:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.StandbyCurrent, axis, 0)
            elif basename == 'rightswitchenable':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.RightLimitSwitchDisable, axis, 0)
            elif basename == 'leftswitchenable':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.LeftLimitSwitchDisable, axis, 0)
            elif basename == 'freewheelingdelay':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.FreewheelingDelay, axis, 0)
            elif basename == 'maxspeed:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.MaximumPositioningSpeed, axis, 0)
            elif basename == 'maxacceleration:raw':
                msg = TMCLPack(Instructions.GetAxisParameter, AxisParameters.MaximumAcceleration, axis, 0)
            elif basename == 'softleft':
                lims = self.readMotorPosFile()
                self.updateVariable(variablename, lims[axis][1][0])
            elif basename == 'softright':
                lims = self.readMotorPosFile()
                self.updateVariable(variablename, lims[axis][1][1])
            elif basename == 'moving':
                if not self.getVariable(variablename).hasValidValue():
                    self.updateVariable(variablename, False)
            elif basename == 'movestartposition':
                if not self.getVariable(variablename).hasValidValue():
                    self.updateVariable(variablename, None)
            elif basename == 'lastmovewassuccessful':
                if not self.getVariable(variablename).hasValidValue():
                    self.updateVariable(variablename, True)
            else:
                raise ValueError(f'Unknown variable {basename} for axis {axis}')
        if msg:
            self.enqueueHardwareMessage(msg)

    def _cutmessages(self, message: bytes) -> Tuple[List[bytes], bytes]:
        msgs = []
        while len(message) >= 9:
            msgs.append(message[:9])
            message = message[9:]
        return msgs, message

    def interpretMessage(self, message: bytes, sentmessage: bytes):
        assert len(sentmessage) == 9
        try:
            cmd, value = TMCLUnpack(message, sentmessage[1])
        except TMCLError:
            raise  # ToDo
        if cmd == Instructions.GetFirmwareVersion:
            self.updateVariable(
                'firmwareversion',
                f'TMCM{value // 0x10000:d}, '
                f'firmware v{(value % 0x10000) // 0x100:d}.{value % 0x100:d}')
        elif cmd == Instructions.MoveTo:
            axis = sentmessage[3]
            self.motionstatus[axis].cmdacktime = time.monotonic()
        elif cmd == Instructions.Stop:
            axis = sentmessage[3]
            if axis in self.motionstatus:
                self.motionstatus[axis].stopcmdacktime = time.monotonic()
        elif cmd == Instructions.GetAxisParameter:
            axisparameter = sentmessage[2]
            axis = sentmessage[3]
            if axisparameter == AxisParameters.TargetPositionReached:
                self.updateVariable(f'targetpositionreached${axis}', bool(value))
            elif axisparameter == AxisParameters.TargetPosition:
                self.updateVariable(f'targetposition:raw${axis}', value)
                self.updateVariable(f'targetposition${axis}', self.converters[axis].position2phys(value))
            elif axisparameter == AxisParameters.ActualPosition:
                self.updateVariable(f'actualposition:raw${axis}', value)
                self.updateVariable(f'actualposition${axis}', self.converters[axis].position2phys(value))
            elif axisparameter == AxisParameters.TargetSpeed:
                self.updateVariable(f'targetspeed:raw${axis}', value)
                self.updateVariable(f'targetspeed${axis}', self.converters[axis].speed2phys(value))
            elif axisparameter == AxisParameters.ActualSpeed:
                self.updateVariable(f'actualspeed:raw${axis}', value)
                self.updateVariable(f'actualspeed${axis}', self.converters[axis].speed2phys(value))
            elif axisparameter == AxisParameters.RightLimitSwitchStatus:
                self.updateVariable(f'rightswitchstatus${axis}', bool(value))
            elif axisparameter == AxisParameters.LeftLimitSwitchStatus:
                self.updateVariable(f'leftswitchstatus${axis}', bool(value))
            elif axisparameter == AxisParameters.ActualAcceleration:
                self.updateVariable(f'actualacceleration:raw${axis}', value)
                self.updateVariable(f'actualacceleration${axis}', self.converters[axis].accel2phys(value))
            elif axisparameter == AxisParameters.ActualLoadValue:
                self.updateVariable(f'load${axis}', value)
            elif axisparameter == AxisParameters.DriverErrorFlags:
                self.updateVariable(f'drivererror${axis}', value)
            elif axisparameter == AxisParameters.RampMode:
                self.updateVariable(f'rampmode${axis}', value)
            elif axisparameter == AxisParameters.PulseDivisor:
                self.updateVariable(f'pulsedivisor${axis}', value)
                self.converters[axis].pulsedivisor = value
                self.reconvertAllRawToPhys(axis)
            elif axisparameter == AxisParameters.RampDivisor:
                self.updateVariable(f'rampdivisor${axis}', value)
                self.converters[axis].rampdivisor = value
                self.reconvertAllRawToPhys(axis)
            elif axisparameter == AxisParameters.MicrostepResolution:
                self.updateVariable(f'microstepresolution${axis}', value)
                self.converters[axis].microstepresolution = value
                self.reconvertAllRawToPhys(axis)
            elif axisparameter == AxisParameters.AbsoluteMaxCurrent:
                self.updateVariable(f'maxcurrent:raw${axis}', value)
                self.updateVariable(f'maxcurrent${axis}', self.converters[axis].current2phys(value))
            elif axisparameter == AxisParameters.StandbyCurrent:
                self.updateVariable(f'standbycurrent:raw${axis}', value)
                self.updateVariable(f'standbycurrent${axis}', self.converters[axis].current2phys(value))
            elif axisparameter == AxisParameters.RightLimitSwitchDisable:
                self.updateVariable(f'rightswitchenable${axis}', not bool(value))
            elif axisparameter == AxisParameters.LeftLimitSwitchDisable:
                self.updateVariable(f'leftswitchenable${axis}', not bool(value))
            elif axisparameter == AxisParameters.FreewheelingDelay:
                self.updateVariable(f'freewheelingdelay${axis}', value / 1000.)
            elif axisparameter == AxisParameters.MaximumPositioningSpeed:
                self.updateVariable(f'maxspeed:raw${axis}', value)
                self.updateVariable(f'maxspeed${axis}', self.converters[axis].speed2phys(value))
            elif axisparameter == AxisParameters.MaximumAcceleration:
                self.updateVariable(f'maxacceleration:raw${axis}', value)
                self.updateVariable(f'maxacceleration${axis}', self.converters[axis].accel2phys(value))
            else:
                raise ValueError(f'Invalid axis parameter: {axisparameter}')
            if axis in self.motionstatus:
                self.checkMotion(axis)
        elif cmd == Instructions.SetAxisParameter:
            pass  # nothing needs to be done
        else:
            raise ValueError(f'TMCL command {cmd} not implemented.')

    def reconvertAllRawToPhys(self, axis: int):
        for varbasename in self.position_variables:
            try:
                self.updateVariable(
                    f'{varbasename}${axis}',
                    self.converters[axis].position2phys(
                        self[f'{varbasename}:raw${axis}']))
            except IndexError:
                pass
        for varbasename in self.current_variables:
            try:
                self.updateVariable(
                    f'{varbasename}${axis}',
                    self.converters[axis].current2phys(
                        self[f'{varbasename}:raw${axis}']))
            except IndexError:
                pass
        for varbasename in self.speed_variables:
            try:
                self.updateVariable(
                    f'{varbasename}${axis}',
                    self.converters[axis].speed2phys(
                        self[f'{varbasename}:raw${axis}']))
            except IndexError:
                pass
        for varbasename in self.acceleration_variables:
            try:
                self.updateVariable(
                    f'{varbasename}${axis}',
                    self.converters[axis].accel2phys(
                        self[f'{varbasename}:raw${axis}']))
            except IndexError:
                pass

    def issueCommand(self, name: str, args: Sequence[Any]):
        if name == 'moveto':
            motorindex, position = args
            self.startMoving(motorindex, position, False)
            # commandFinished or commandFailed will be called by startmoving()
        elif name == 'moverel':
            motorindex, position = args
            self.startMoving(motorindex, position, True)
            # commandFinished or commandFailed will be called by startmoving()
        elif name == 'stop':
            motorindex, = args
            if motorindex < 0 or motorindex >= self.Naxes:
                self.commandError(name, f'Invalid motor index: {motorindex}')
            else:
                self.enqueueHardwareMessage(TMCLPack(Instructions.Stop, 0, motorindex, 0))
                self.commandFinished(name, f'Stopping motor #{motorindex}')
                if motorindex in self.motionstatus:
                    # note that stopping a motor should always work, even in the case of internal inconsistency
                    self.motionstatus[motorindex].stopcmdenquetime = time.monotonic()
        elif name == 'setposition':
            motorindex, position = args
            # ensure that ramp mode is 2: speed mode. If we are in position mode (ramp mode = 1), changing the
            # target or the actual position starts moving the motor.
            if motorindex < 0 or motorindex >= self.Naxes:
                self.commandError(name, f'Invalid motor index: {motorindex}')
            else:
                self.enqueueHardwareMessage(
                    TMCLPack(Instructions.SetAxisParameter, AxisParameters.RampMode, motorindex, 2))
                rawposition = self.converters[motorindex].position2raw(position)
                self.enqueueHardwareMessage(
                    TMCLPack(Instructions.SetAxisParameter, AxisParameters.ActualPosition, motorindex, rawposition))
                self.enqueueHardwareMessage(
                    TMCLPack(Instructions.SetAxisParameter, AxisParameters.TargetPosition, motorindex, rawposition))
                self.wakeautoquery.set()
                self.queryVariable(f'actualposition${motorindex}')
                self.queryVariable(f'targetposition${motorindex}')
                self.commandFinished(name, f"Position of motor #{motorindex} set to {position}")
        elif name == 'setlimits':
            # Set software limits: left and right
            motorindex, (left, right) = args
            if motorindex < 0 or motorindex >= self.Naxes:
                self.commandError(name, f'Invalid motor index: {motorindex}')
            elif left > right:
                self.commandError(name, f'Left limit is larger than the right one.')
            else:
                self.updateVariable(f'softleft${motorindex}', left)
                self.updateVariable(f'softright${motorindex}', right)
                self.commandFinished(name, f'Set limits for motor #{motorindex}')
        else:
            self.commandError(name, 'Unknown command')

    def readMotorPosFile(self) -> Dict[int, Tuple[float, Tuple[float]]]:
        # Content of a motor position file:
        # 0: 0.0000000000000000 (0.0000000000000000, 0.0000000000000000)
        # 1: 12.1435937500000009 (-18.0000000000000000, 17.0000000000000000)
        # 2: 34.5499218750000026 (0.0000000000000000, 73.0000000000000000)
        motorpos = dict(zip(range(self.Naxes), itertools.repeat((0.0, (0.0, 0.0)))))
        with open(self.positionfile) as f:
            for iline, line in enumerate(f, start=1):
                m = re.match(
                    r'^\s*(?P<axis>\d+):'
                    r'\s*(?P<position>[+-]?\d+\.\d+)\s+'
                    r'\((?P<softleft>[+-]?\d+\.\d+)\s*,\s*(?P<softright>[+-]?\d+\.\d+)\s*\)\s*$', line.strip())
                if not m:
                    self.warning(
                        f'Cannot interpret line {iline} in motor position file {self.positionfile}: {line.strip()}')
                axis = int(m['axis'])
                position = float(m['position'])
                softleft = float(m['softleft'])
                softright = float(m['softright'])
                if axis < 0 or axis >= self.Naxes:
                    continue
                motorpos[axis] = (position, (softleft, softright))
        return motorpos

    def writeMotorPosFile(self):
        with open(self.positionfile, 'wt') as f:
            for axis in range(self.Naxes):
                pos = self.converters[axis].position2phys(self[f'actualposition${axis}'])
                f.write(f'{axis}: {pos:.16f} '
                        f'({self[f"softleft${axis}"]:.16f}, '
                        f'{self[f"softright${axis}"]:.16f})\n')

    def startMoving(self, axis: int, position: float, relative: bool = False):
        if axis in self.motionstatus:
            self.commandError('moverel' if relative else 'moveto', f'Motor {axis} already moving.')
            return
        actualposition = self[f'actualposition${axis}']
        if ((relative and position == 0) or  # relative move by 0 steps
                ((not relative) and position == actualposition)):  # absolute move to the same position
            # simulate a start and end of a motion.
            self.updateVariable('__status__', self.Status.Moving)
            self.updateVariable('__auxstatus__', ', '.join([str(i) for i in sorted(list(self.motionstatus) + [axis])]))
            self.updateVariable(f'movestartposition${axis}', actualposition)
            self.updateVariable(f'moving${axis}', True)
            self.commandFinished('moverel' if relative else 'moveto', f'Simulating zero-move of motor #{axis}')
            self.updateVariable(f'lastmovewassuccessful${axis}', True)
            self.updateVariable('__status__', self.Status.Moving if self.motionstatus else self.Status.Idle)
            self.updateVariable('__auxstatus__', ', '.join([str(i) for i in sorted(self.motionstatus)]))
            self.updateVariable(f'moving${axis}', False)
            return
        # check soft limits
        softleft = self[f'softleft${axis}']
        softright = self[f'softright${axis}']
        if ((not relative) and
            ((position < softleft) or
             (position > softright))) or \
                (relative and
                 ((actualposition + position < softleft) or
                  (actualposition + position > softright))):
            self.commandError(
                'moverel' if relative else 'moveto',
                f'Cannot move motor #{axis}: target position ({position}) is outside the software limits '
                f'({softleft}, {softright}).')
            return
        if (actualposition < softleft) or (actualposition > softright):
            self.commandError('moverel' if relative else 'moveto', f'Actual position is outside the limits')
            return
        # self.debug(f'Now starting moving motor #{axis}')
        # create a status entry for this motor
        self.motionstatus[axis] = MotionData(axis)
        if relative and position < 0:
            self.motionstatus[axis].direction = 'left'
        elif relative and position > 0:
            self.motionstatus[axis].direction = 'right'
        elif (not relative) and (position - self[f'actualposition${axis}']) > 0:
            self.motionstatus[axis].direction = 'right'
        elif (not relative) and (position - self[f'actualposition${axis}']) < 0:
            self.motionstatus[axis].direction = 'left'
        else:
            assert False
        rawtargetposition = self.converters[axis].position2raw(position)
        # boost the update frequency of some variables which are expected to change:
        for varbasename in ['actualspeed', 'actualposition', 'targetpositionreached', 'leftswitchstatus',
                            'rightswitchstatus', 'load', 'targetspeed', 'rampmode', 'actualacceleration']:
            varname = f'{varbasename}${axis}'
            self.getVariable(varname).setTimeout(self.motion_query_timeout)
            # self.debug(f'Set query timeout of variable {varname} to {self.getVariable(varname).querytimeout}')
        self.wakeautoquery.set()
        # issue the MVP (move to position) command
        self.enqueueHardwareMessage(
            TMCLPack(cmdnum=Instructions.MoveTo, typenum=1 if relative else 0, motor_or_bank=axis,
                     value=rawtargetposition))
        # self.debug('Enqueued moveto message')
        # some variables are not queried by default. Query these once.
        self.queryVariable(f'targetposition${axis}')
        self.motionstatus[axis].cmdenqueuetime = time.monotonic()
        self.updateVariable(f'movestartposition${axis}', actualposition)
        self.updateVariable('__status__', self.Status.Moving)
        self.updateVariable('__auxstatus__', ', '.join([str(i) for i in sorted(self.motionstatus)]))
        self.updateVariable(f'moving${axis}', True)
        self.commandFinished('moverel' if relative else 'moveto', f'Starting motor #{axis}')

    def motionEnded(self, axis: int, successful: bool):
        # set query timeouts back to normal
        self.debug(f'Motion of motor {axis} ended.')
        for varbasename in ['actualspeed', 'actualposition', 'targetpositionreached', 'leftswitchstatus',
                            'rightswitchstatus', 'load', 'targetspeed', 'rampmode', 'actualacceleration']:
            varname = f'{varbasename}${axis}'
            self.getVariable(varname).setTimeout(None)
        del self.motionstatus[axis]
        self.updateVariable('__status__', self.Status.Moving if self.motionstatus else self.Status.Idle)
        self.updateVariable('__auxstatus__', ', '.join([str(i) for i in sorted(self.motionstatus)]))
        self.updateVariable(f'lastmovewassuccessful${axis}', successful)
        self.updateVariable(f'moving${axis}', False)

    def checkMotion(self, axis: int) -> bool:
        """Check if a motor is (still) moving and act if it has stopped.

        To minimize dead time, we want to detect motor stop very quickly and very accurately.
        """
        if axis not in self.motionstatus:
            return False  # the motor is not moving, and we do not need to do anything about it.

        if self.motionstatus[axis].cmdacktime is None:
            # we did not yet get the acknowledgement message for the MoveTo command from the controller, assume that the
            # motor is moving
            return True  # the motor is assumed to be moving (or will be moving shortly)

        if self.motionstatus[axis].targetposition is None:
            # try to get the target position if we do not have a value for it
            targetposition = self.getVariable(f'targetposition${axis}')
            if targetposition.timestamp > self.motionstatus[axis].cmdacktime:
                self.motionstatus[axis].targetposition = targetposition.value
                # we don't need to query it too fast
                targetposition.setTimeout(None)

        # note that the variables can be outdated. Before making decisions based on their values, make sure that
        # we have a recent enough value, i.e. after the start of the motion

        actualposition = self.getVariable(f'actualposition${axis}')
        actualspeed = self.getVariable(f'actualspeed${axis}')
        targetpositionreached = self.getVariable(f'targetpositionreached${axis}')
        #        self.debug(str(actualposition))
        #        self.debug(str(actualspeed))
        #        self.debug(str(targetpositionreached))

        # Stop condition #1: if the actual position is the same as targetposition and targetpositionreached is True
        if ((actualposition.timestamp > self.motionstatus[axis].cmdacktime) and
                (targetpositionreached.timestamp > self.motionstatus[axis].cmdacktime) and
                (self.motionstatus[axis].targetposition is not None) and
                (actualposition.value == self.motionstatus[axis].targetposition) and
                (targetpositionreached.value is True)):
            # successful motor stop
            self.debug('Stop condition #1 (target reached) met.')
            self.motionEnded(axis, True)
            return False  # motor stopped

        # Stop condition #2: the speed is zero and the corresponding end switch is hit
        if self.motionstatus[axis].direction == 'left':
            switchstatus = self.getVariable(f'leftswitchstatus${axis}')
            switchenabled = self[f'leftswitchenable${axis}']
        elif self.motionstatus[axis].direction == 'right':
            switchstatus = self.getVariable(f'rightswitchstatus${axis}')
            switchenabled = self[f'rightswitchenable${axis}']
        else:
            assert False

        #        self.debug(f'Direction: {self.motionstatus[axis].direction}')
        #        self.debug(f'Switch status: {switchstatus.value}. Switch enabled: {switchenabled}')

        if ((self.motionstatus[axis].cmdacktime is not None) and
                (actualspeed.timestamp > self.motionstatus[axis].cmdacktime) and
                (switchstatus.timestamp > self.motionstatus[axis].cmdacktime) and
                (switchstatus.value is True) and switchenabled):
            self.debug('Stop condition #2 (end switch) met.')
            self.motionEnded(axis, False)
            return False

        # Stop condition #3: user stop
        if ((self.motionstatus[axis].stopcmdacktime is not None) and
                (actualspeed.timestamp > self.motionstatus[axis].stopcmdacktime) and
                (actualspeed.value == 0)):
            # motor stop by user break
            self.debug('Stop condition #3 (user stop) met.')
            self.motionEnded(axis, False)
            return False

        #        self.debug('Still moving.')
        return True

    def onVariablesReady(self):
        self.updateVariable('__status__', self.Status.Idle)
        self.updateVariable('__auxstatus__', '')


class TMCM351Backend(TrinamicMotorControllerBackend):
    name = 'tmcm351'
    Naxes: int = 3
    topRMScurrent: float = 2.8
    max_microsteps: int = 6
    clock_frequency: int = 16000000
    full_step_size: float = 1 / 200.


class TMCM6110Backend(TrinamicMotorControllerBackend):
    name = 'tmcm6110'
    Naxes: int = 6
    topRMScurrent: float = 1.1
    max_microsteps: int = 8
    clock_frequency: int = 16000000
    full_step_size: float = 1 / 200.