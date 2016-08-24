import datetime
import logging
from typing import Optional, Union, Dict

import dateutil.parser
from sastool.misc.errorvalue import ErrorValue

from .service import Service, ServiceError
from ..utils.callback import SignalFlags

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SampleStoreError(ServiceError):
    pass


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
        dic = self.todict()
        return '\n'.join(['sample.' + k + ':\t' + str(dic[k]) for k in dic]) + '\n'

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
        return 'Sample({0.title}, ({0.positionx:.3f}, {0.positiony:.3f}), {0.thickness:.4f}, {0.transmission:.4f})'.format(
            self)

    def __str__(self):
        return '{0.title}, ({0.positionx:.3f}, {0.positiony:.3f}), {0.thickness:.4f} cm, transm: {0.transmission:.4f}'.format(
            self)

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

    def __gt__(self, other):
        return self.title > other.title

    def __lt__(self, other):
        return self.title < other.title

    def __le__(self, other):
        return self.title <= other.title


class SampleStore(Service):
    __signals__ = {'list-changed': (SignalFlags.RUN_FIRST, None, ()),
                   'active-changed': (SignalFlags.RUN_FIRST, None, ()),
                   }

    name = 'samplestore'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._list = []
        self._active = None

    def load_state(self, dictionary: Dict):
        super().load_state(dictionary)
        if isinstance(dictionary['list'], list):
            self._list = [Sample.fromdict(sampledict)
                          for sampledict in dictionary['list']]
        else:
            self._list = [Sample.fromdict(sampledict) for sampledict in dictionary['list'].values()]
        self._list = sorted(self._list, key=lambda s: s.title)
        self._active = dictionary['active']
        self.emit('list-changed')

    def save_state(self):
        dic = super().save_state()
        dic['active'] = self._active
        dic['list'] = {x.title: x.todict() for x in self._list}
        return dic

    def add(self, sample: Sample):
        if not [s for s in self._list if s.title == sample.title]:
            self._list.append(sample)
            self._list = sorted(self._list, key=lambda x: x.title)
            self.emit('list-changed')
        else:
            return False
        return True

    def remove(self, sample: Union[Sample, str]):
        if isinstance(sample, Sample):
            sample = sample.title
        if not [s for s in self._list if s.title == sample]:
            raise KeyError('Unknown sample with title ' + str(sample))
        self._list = [s for s in self._list if s.title != sample]
        if sample == self._active:
            try:
                self._active = self._list[0]
            except IndexError:
                self._active = None
            self.emit('active-changed')
        self.emit('list-changed')

    def set_active(self, sample: Optional[str]):
        """sample: string or None"""
        if sample is None:
            self._active = None
            self.emit('active-changed')
            return
        elif isinstance(sample, Sample):
            sample = sample.title
        else:
            sample = str(sample)
        if [s for s in self._list if s.title == sample]:
            self._active = sample
            self.emit('active-changed')
        else:
            raise SampleStoreError('No sample {} defined.'.format(sample))

    def get_active(self):
        if self._active is None:
            return None
        else:
            try:
                return [x for x in self._list if x.title == self._active][0]
            except IndexError:
                self._active = None
                return None

    def get_active_name(self):
        a = self.get_active()
        if a is None:
            return None
        else:
            return a.title

    def __iter__(self):
        for l in self._list:
            yield l

    def get_sample(self, title: str):
        sample = [s for s in self._list if s.title == title]
        if not sample:
            raise KeyError('Unknown sample:', title)
        assert (len(sample) == 1)  # there should be only one sample titled `title`
        return sample[0]

    def set_sample(self, title: str, sample: Sample):
        self._list = sorted([s for s in self._list if s.title != title] + [sample], key=lambda x: x.title)
        self.emit('list-changed')

    def __contains__(self, samplename: str):
        return bool([s for s in self._list if s.title == samplename])
