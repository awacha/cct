import struct
from typing import Optional, Tuple


class TMCLError(Exception):
    pass


class TMCLStatusMessage:
    Wrong_checksum = 1
    Invalid_command = 2
    Wrong_type = 3
    Invalid_value = 4
    Configuration_EEPROM_locked = 5
    Command_not_available = 6
    Success = 100
    Loaded_into_TMCL_EEPROM = 101

    @classmethod
    def interpretErrorCode(cls, code: int) -> str:
        for code_, message in [
            (cls.Wrong_checksum, 'Wrong checksum'),
            (cls.Invalid_command, 'Invalid command'),
            (cls.Wrong_type, 'Wrong type'),
            (cls.Invalid_value, 'Invalid value'),
            (cls.Configuration_EEPROM_locked, 'Configuration EEPROM locked'),
            (cls.Command_not_available, 'Command not available'),
            (cls.Success, 'Success'),
            (cls.Loaded_into_TMCL_EEPROM, 'Command loaded into TMCL program EEPROM')
        ]:
            if code == code_:
                return message
        else:
            raise ValueError(f'Unknown TMCL status number: {code}')


def TMCLPack(cmdnum: int, typenum: int, motor_or_bank: int, value: int) -> bytes:
    """Construct the bytes representation of the command and send it to the
    TMCM card. The bytes are:
    - Module address (always 1)
    - Command number
    - Type number
    - Motor or Bank number
    - Value (MSB)
    - Value
    - Value
    - Value (LSB)
    - Checksum: the sum of all the previous bytes, module 256.

    In total, 9 bytes compose the sent message.
    """
    cmd = bytes([1, cmdnum, typenum, motor_or_bank]) + struct.pack('>i', int(value))
    cmd = cmd + bytes([sum(cmd) % 256])
    return cmd


def TMCLUnpack(message: bytes, sentmessage: Optional[bytes] = None) -> Tuple[int, int, int]:
    """Unpacks a TMCL reply message

    # messages are composed of 9 bytes:
    #  reply address (typically 2)
    #  target address (typically 1)
    #  status (see the values of the TMCLStatusMessage class)
    #  instruction (the code of the instruction to which this is a reply)
    #  MSB of the 4-byte value
    #  2nd byte of the value
    #  3rd byte of the value
    #  LSB of the 4-byte value
    #  checksum: sum of the previous 8 bytes modulo 256
    """
    # first check the message length
    if len(message) != 9:
        raise TMCLError(f'Invalid message length: got {len(message)} bytes instead of 9')
    # check the checksum
    if sum(message[:-1]) % 256 != message[-1]:
        raise TMCLError(f'Checksum error on TMCL message "{message}"')
    # check the error status
    status = message[2]
#    if status != TMCLStatusMessage.Success:
#        raise TMCLError(f'Got error message from TMCM controller: "{TMCLStatusMessage.interpretErrorCode(status)} '
#                        f'(code {status})"')
    # if we can, check if we got the reply for the correct command
    if (sentmessage[1] is not None) and (sentmessage[1] != message[3]):
        raise TMCLError(f'Got reply for command {message[3]}, expected {sentmessage[1]}. Sent message: {sentmessage}')
    return status, message[3], struct.unpack('>i', message[4:8])[0]


class AxisParameters:
    TargetPosition = 0
    ActualPosition = 1
    TargetSpeed = 2
    ActualSpeed = 3
    MaximumPositioningSpeed = 4
    MaximumAcceleration = 5
    AbsoluteMaxCurrent = 6
    StandbyCurrent = 7
    TargetPositionReached = 8
    ReferenceSwitchStatus = 9
    RightLimitSwitchStatus = 10
    LeftLimitSwitchStatus = 11
    RightLimitSwitchDisable = 12
    LeftLimitSwitchDisable = 13
    MinimumSpeed = 130
    ActualAcceleration = 135
    RampMode = 138
    MicrostepResolution = 140
    ReferenceSwitchTolerance = 141
    SoftStopFlag = 149
    RampDivisor = 153
    PulseDivisor = 154
    StepInterpolationEnable = 160  # only for TMCM6110
    DoubleStepEnable = 161  # only for TMCM6110
    ChopperBlankTime = 162  # only for TMCM6110
    ChopperMode = 163  # only for TMCM6110
    ChopperHysteresisDecrement = 164  # only for TMCM6110
    ChopperHysteresisEnd = 165  # only for TMCM6110
    ChopperHysteresisStart = 166  # only for TMCM6110
    ChopperOffTime = 167  # only for TMCM6110
    SmartEnergyCurrentMinimum = 168  # only for TMCM6110
    SmartEnergyCurrentDownStep = 169  # only for TMCM6110
    SmartEnergyHysteresis = 170  # only for TMCM6110
    SmartEnergyCurrentUpStep = 171  # only for TMCM6110
    SmartEnergyHysteresisStart = 172  # only for TMCM6110
    StallGuard2FilterEnable = 173  # only for TMCM6110
    StallGuard2Threshold = 174  # only for TMCM6110
    SlopeControlHighSide = 175  # only for TMCM6110
    SlopeControlLowSide = 176  # only for TMCM6110
    ShortProtectionDisable = 177  # only for TMCM6110
    ShortDetectionTimer = 178  # only for TMCM6110
    Vsense = 179  # only for TMCM6110
    SmartEnergyActualCurrent = 180  # only for TMCM6110
    StopOnStall = 181  # only for TMCM6110
    SmartEnergyThresholdSpeed = 182  # only for TMCM6110
    SmartEnergySlowRunCurrent = 183  # only for TMCM6110
    RandomChopperOffTime = 184  # only for TMCM6110
    ReferenceSearchMode = 193
    ReferenceSearchSpeed = 194
    ReferenceSwitchSpeed = 195
    ReferenceSwitchDistance = 196
    LastReferencePosition = 197  # only for TMCM6110
    BoostCurrent = 200
    MixedDecayThreshold = 203
    FreewheelingDelay = 204
    StallDetectionThreshold = 205 # only for TMCM351
    ActualLoadValue = 206
    ExtendedErrorFlags = 207
    DriverErrorFlags = 208  # actual interpretation of the flags different for TMCM351 and TMCM6110
    EncoderPosition = 209  # Only for TMCM351
    EncoderPrescaler = 210  # Only for TMCM351
    FullstepThreshold = 211  # Only for TMCM351
    MaximumEncoderDeviation = 212  # Only for TMCM351
    GroupIndex = 213
    PowerDownDelay = 214


class Instructions:
    RotateRight = 1
    RotateLeft  = 2
    Stop = 3
    MoveTo = 4
    SetAxisParameter = 5
    GetAxisParameter = 6
    StoreAxisParameter = 7
    RestoreAxisParameter = 8
    SetGlobalParameter = 9
    GetGlobalParameter = 10
    StoreGlobalParameter = 11
    RestoreGlobalParameter = 12
    ReferenceSearch = 13
    SetInputOutput = 14
    GetInputOUtput = 15
    Calculate = 19
    Compare = 20
    JumpConditional = 21
    JumpAlways = 22
    CallSubroutine = 23
    ReturnFromSubroutine = 24
    Wait = 27
    StopTMCLProgram = 28
    SetCoordinate = 30
    GetCoordinate = 31
    CaptureCoordinate = 32
    AccuToCoordinate = 39
    CalculateX = 33
    AccuToAxisParameter = 34
    AccuToGlobalParameter = 35
    ClearErrorFlags = 36
    SetInterruptVector = 37
    EnableInterrupt = 25
    DisableInterrupt = 26
    ReturnFromInterrupt = 38
    RequestTargetPositionReachedEvent = 138
    GetFirmwareVersion = 136
    ResetToFactoryDefaults = 137
