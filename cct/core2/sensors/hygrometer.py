from .sensor import Sensor


class Hygrometer(Sensor):
    sensortype = 'hygrometer'
    quantityname = 'relative humidity'
