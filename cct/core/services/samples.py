from .service import Service, ServiceError
from ..instrument.sample import Sample
from sastool.misc.errorvalue import ErrorValue
import dateutil.parser
import os


class SampleStoreError(ServiceError):
    pass


class SampleStore(Service):

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._list = []
        self._active = None

    def _load_state(self, dictionary):
        Service._load_state(self, dictionary)
        self._list = [Sample.fromdict(sampledict)
                      for sampledict in dictionary['list']]
        self._active = dictionary['active']
        try:
            with open(os.path.join(self.instrument.config['path']['directories']['config'], 'samples.conf'), 'rt', encoding='utf-8') as f:
                for l in f:
                    try:
                        rhs = l.split('=', 1)[1].strip()
                    except IndexError:
                        pass
                    if l.startswith('['):
                        sample = {}
                    elif l.startswith('title ='):
                        sample['title'] = rhs
                    elif l.startswith('positionx ='):
                        sample['positionx'] = ErrorValue(float(rhs), 0)
                    elif l.startswith('positionxerror ='):
                        sample['positionx'].err = float(rhs)
                    elif l.startswith('positiony ='):
                        sample['positiony'] = ErrorValue(float(rhs), 0)
                    elif l.startswith('positionyerror ='):
                        sample['positiony'].err = float(rhs)
                    elif l.startswith('transmission ='):
                        sample['transmission'] = ErrorValue(float(rhs), 0)
                    elif l.startswith('transmissionerror ='):
                        sample['transmission'].err = float(rhs)
                    elif l.startswith('thickness ='):
                        sample['thickness'] = ErrorValue(float(rhs), 0)
                    elif l.startswith('thicknesserror ='):
                        sample['thickness'].err = float(rhs)
                    elif l.startswith('distminus ='):
                        sample['distminus'] = ErrorValue(float(rhs), 0)
                    elif l.startswith('distminuserror ='):
                        sample['distminus'].err = float(rhs)
                    elif l.startswith('prepareby ='):
                        sample['preparedby'] = rhs
                    elif l.startswith('preparetime ='):
                        sample['preparetime'] = dateutil.parser.parse(rhs)
                    elif l.startswith('description ='):
                        sample['description'] = rhs
                    elif l.startswith('category ='):
                        sample['category'] = rhs
                    elif l.startswith('situation ='):
                        sample['situation'] = rhs
                    else:
                        self.add(Sample(**sample))
        except IOError:
            pass

    def _save_state(self):
        dic = Service._save_state(self)
        dic['active'] = self._active
        dic['list'] = [x.todict() for x in self._list]
        return dic

    def add(self, sample):
        if not [s for s in self._list if s.title == sample.title]:
            self._list.append(sample)
        if self._active is None:
            self._active = sample.title

    def remove(self, sample):
        self._list = [s for s in self._list if s.title != sample.title]

    def set_active(self, sample):
        if isinstance(sample, Sample):
            sample = sample.name
        if [s for s in self._list if s.title == sample]:
            self._active = sample
        else:
            raise SampleStoreError('No sample %s defined.' % sample)

    def get_active(self):
        return [x for x in self._list if x.title == self._active][0]

    def __iter__(self):
        for l in self._list:
            yield l
