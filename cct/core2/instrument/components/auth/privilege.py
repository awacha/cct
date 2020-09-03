import enum


class Privilege(enum.Enum):
    Shutter = 'SH'
    MoveMotors = 'MT'
    MoveBeamstop = 'BS'
    ConnectDevices = 'CD'
    MovePinholes = 'PH'
    ProjectManagement = 'PR'
    MotorCalibration = 'MC'
    DeviceConfiguration = 'DC'
    UserManagement = 'UM'
    SuperUser = 'SU'
