import datetime

import dateutil.parser
from sastool.misc.errorvalue import ErrorValue

VALID_CATEGORIES = ['calibration sample',
                    'normalization sample', 'sample', 'sample+can', 'can', 'none']

VALID_SITUATIONS = ['air', 'vacuum', 'sealed can']


class Sample(object):
    title = None
    positionx = 0.0
    positiony = 0.0
    thickness = 1.0
    transmission = 1.0
    preparedby = 'Anonymous'
    preparetime = None
    distminus = 0.0
    description = ''
    category = None  # a string. Can be any element of VALID_CATEGORIES
    situation = None  # a string. Can be any element of VALID_SITUATIONS

    @classmethod
    def fromdict(cls, dic):
        return cls(title=dic['title'],
                   positionx=ErrorValue(
                       dic['positionx.val'], dic['positionx.err']),
                   positiony=ErrorValue(
                       dic['positiony.val'], dic['positiony.err']),
                   thickness=ErrorValue(
                       dic['thickness.val'], dic['thickness.err']),
                   transmission=ErrorValue(
                       dic['transmission.val'], dic['transmission.err']),
                   preparedby=dic['preparedby'],
                   preparetime=dateutil.parser.parse(dic['preparetime']),
                   distminus=ErrorValue(
                       dic['distminus.val'], dic['distminus.err']),
                   description=dic['description'],
                   category=dic['category'],
                   situation=dic['situation'],
                   )

    def todict(self):
        return {'title': self.title,
                'positionx.val': self.positionx.val,
                'positionx.err': self.positionx.err,
                'positiony.val': self.positiony.val,
                'positiony.err': self.positiony.err,
                'thickness.val': self.thickness.val,
                'thickness.err': self.thickness.err,
                'transmission.val': self.transmission.val,
                'transmission.err': self.transmission.err,
                'preparedby': self.preparedby,
                'preparetime': str(self.preparetime),
                'distminus.val': self.distminus.val,
                'distminus.err': self.distminus.err,
                'description': self.description,
                'category': self.category,
                'situation': self.situation}

    def toparam(self):
        return '\n'.join(['sample.' + k + ':\t%s' % v for k, v in self.todict()]) + '\n'

    def __init__(self, title, positionx=0.0, positiony=0.0, thickness=1.0,
                 transmission=1.0, preparedby='Anonymous', preparetime=None,
                 distminus=0.0, description='', category='sample', situation='vacuum'):

        if isinstance(title, self.__class__):
            self.title = title.title
            self.positionx = title.positionx
            self.positiony = title.positiony
            self.thickness = title.thickness
            self.transmission = title.transmission
            self.preparedby = title.preparedby
            self.preparetime = title.preparetime
            self.distminus = title.distminus
            self.description = title.description
            self.category = title.category
            self.situation = title.situation
        else:
            self.title = title
            self.positionx = positionx
            self.positiony = positiony
            self.thickness = thickness
            self.transmission = transmission
            self.preparedby = preparedby
            self.category = category
            if preparetime is None:
                preparetime = datetime.datetime.now()
            self.preparetime = preparetime
            self.distminus = distminus
            self.description = description
            self.situation = situation
        if not isinstance(self.positionx, ErrorValue):
            self.positionx = ErrorValue(self.positionx, 0)
        if not isinstance(self.positiony, ErrorValue):
            self.positiony = ErrorValue(self.positiony, 0)
        if not isinstance(self.thickness, ErrorValue):
            self.thickness = ErrorValue(self.thickness, 0)
        if not isinstance(self.transmission, ErrorValue):
            self.transmission = ErrorValue(self.transmission, 0)
        if not isinstance(self.distminus, ErrorValue):
            self.distminus = ErrorValue(self.distminus, 0)

    def __repr__(self):
        return 'Sample(%s, (%.3f, %.3f), %.4f, %.4f)' % (self.title,
                                                         self.positionx, self.positiony, self.thickness, self.transmission)

    def __str__(self):
        return '%s, (%.3f, %.3f), %.4f cm, transm: %.4f' % (self.title,
                                                            self.positionx, self.positiony, self.thickness, self.transmission)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.title == other.title
        elif isinstance(other, str):
            return self.title == other
        else:
            return NotImplemented

    def __ne__(self, other):
        return not (self == other)

    def get_header(self):
        hed = {'Title': self.title, 'Preparedby':
               self.preparedby, 'Preparetime': self.preparetime,
               'SampleDescription': self.description}
        for attr, key in [('thickness', 'Thickness'),
                          ('transmission', 'Transm'),
                          ('positiony', 'PosSample'),
                          ('positionx', 'PosSampleX'),
                          ('distminus', 'DistMinus'),
                          ]:
            hed[key] = float(self.__getattribute__(attr))
            if isinstance(self.__getattribute__(attr), ErrorValue):
                hed[key + 'Error'] = self.__getattribute__(attr).err
        return hed

    def __ge__(self, other):
        return self.title >= other.title

    def __eq__(self, other):
        return self.title == other.title

    def __gt__(self, other):
        return self.title > other.title

    def __lt__(self, other):
        return self.title < other.title

    def __le__(self, other):
        return self.title <= other.title

    def __ne__(self, other):
        return self.title != other.title
