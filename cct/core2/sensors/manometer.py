from .sensor import Sensor


class Manometer(Sensor):
    sensortype = 'manometer'
    quantityname = 'pressure'
