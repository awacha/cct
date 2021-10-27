"""Convert raw TMCM parameters to physical values"""


class UnitConverter:
    """Helper class to convert between raw and physical values of current, position, speed and acceleration"""
    top_rms_current: float  # maximum root mean square current of the motor controller
    fullstepsize: float  # physical size of a full step, e.g. in degrees or in mm-s.
    clockfreq: float  # clock frequency (Hz) of the TMCM module
    pulsedivisor: int  # pulse divisor of the TMCM module
    rampdivisor: int  # ramp divisor of the TMCM module
    microstepresolution: int  # microstep resolution of the TMCM module

    def __init__(self, top_rms_current: float, fullstepsize: float, clockfreq: float, pulsedivisor: int = 1,
                 rampdivisor: int = 1, microstepresolution: int = 1):
        self.top_rms_current = top_rms_current
        self.fullstepsize = fullstepsize
        self.clockfreq = clockfreq
        self.pulsedivisor = pulsedivisor
        self.rampdivisor = rampdivisor
        self.microstepresolution = microstepresolution

    def current2raw(self, current: float) -> int:
        if current > self.top_rms_current or current < 0:
            raise ValueError(f'Invalid current value: must be between 0 A and {self.top_rms_current} A')
        return int(current * 255 / self.top_rms_current)

    def current2phys(self, current: int) -> float:
        return current * self.top_rms_current / 255.

    def accel2raw(self, accel: float, ) -> int:
        val = int(accel / self.fullstepsize / self.clockfreq ** 2 *
                  2 ** (self.pulsedivisor + self.rampdivisor + self.microstepresolution + 29))
        if val < 0 or val > 2047:
            raise ValueError('Acceleration out of bounds')
        return val

    def accel2phys(self, accel: float) -> float:
        return accel * self.fullstepsize * self.clockfreq ** 2 / \
               2 ** (self.pulsedivisor + self.rampdivisor + self.microstepresolution + 29)

    def speed2raw(self, speed: float) -> int:
        val = int(speed * 2 ** (self.pulsedivisor + self.microstepresolution + 16) / self.clockfreq / self.fullstepsize)
        if val < -2047 or val > 2047:
            raise ValueError('Speed out of bounds.')
        return val

    def speed2phys(self, speed: int) -> float:
        return speed / 2 ** (self.pulsedivisor + self.microstepresolution + 16) * self.clockfreq * self.fullstepsize

    def position2raw(self, position: float) -> int:
        return int(position * 2 ** self.microstepresolution / self.fullstepsize)

    def position2phys(self, position: int):
        return position * self.fullstepsize / 2 ** self.microstepresolution

    def maximumSpeed(self):
        return self.speed2phys(2047)

    def maximumAcceleration(self):
        return self.accel2phys(2047)

    def maximumCurrent(self):
        return self.current2phys(255)

    def speedStep(self):
        return self.speed2phys(1)

    def accelerationStep(self):
        return self.accel2phys(1)

    def currentStep(self):
        return self.current2phys(1)