import logging

from gi.repository import GObject

from .service import Service, ServiceError
from ..instrument.sample import Sample

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SampleStoreError(ServiceError):
    pass


class SampleStore(Service):
    __gsignals__ = {'list-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    'active-changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
                    }

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._list = []
        self._active = None

    def _load_state(self, dictionary):
        Service._load_state(self, dictionary)
        if isinstance(dictionary['list'], list):
            self._list = [Sample.fromdict(sampledict)
                          for sampledict in dictionary['list']]
        else:
            self._list = [Sample.fromdict(sampledict) for sampledict in dictionary['list'].values()]
        self._list = sorted(self._list, key=lambda s: s.title)
        self._active = dictionary['active']
        #        try:
        #            with open(os.path.join(self.instrument.config['path']['directories']['config'], 'samples.conf'), 'rt', encoding='utf-8') as f:
        #                for l in f:
        #                    try:
        #                        rhs = l.split('=', 1)[1].strip()
        #                    except IndexError:
        #                        pass
        #                    if l.startswith('['):
        #                        sample = {}
        #                    elif l.startswith('title ='):
        #                        sample['title'] = rhs
        #                    elif l.startswith('positionx ='):
        #                        sample['positionx'] = ErrorValue(float(rhs), 0)
        #                    elif l.startswith('positionxerror ='):
        #                        sample['positionx'].err = float(rhs)
        #                    elif l.startswith('positiony ='):
        #                        sample['positiony'] = ErrorValue(float(rhs), 0)
        #                    elif l.startswith('positionyerror ='):
        #                        sample['positiony'].err = float(rhs)
        #                    elif l.startswith('transmission ='):
        #                        sample['transmission'] = ErrorValue(float(rhs), 0)
        #                    elif l.startswith('transmissionerror ='):
        #                        sample['transmission'].err = float(rhs)
        #                    elif l.startswith('thickness ='):
        #                        sample['thickness'] = ErrorValue(float(rhs), 0)
        #                    elif l.startswith('thicknesserror ='):
        #                        sample['thickness'].err = float(rhs)
        #                    elif l.startswith('distminus ='):
        #                        sample['distminus'] = ErrorValue(float(rhs), 0)
        #                    elif l.startswith('distminuserror ='):
        #                        sample['distminus'].err = float(rhs)
        #                    elif l.startswith('preparedby ='):
        #                        sample['preparedby'] = rhs
        #                    elif l.startswith('preparetime ='):
        #                        sample['preparetime'] = dateutil.parser.parse(rhs)
        #                    elif l.startswith('description ='):
        #                        sample['description'] = rhs
        #                    elif l.startswith('category ='):
        #                        sample['category'] = rhs
        #                    elif l.startswith('situation ='):
        #                        sample['situation'] = rhs
        #                    else:
        #                        if sample['title'] in self:
        #                            self.remove(sample['title'])
        #                        self.add(Sample(**sample))
        #        except IOError:
        #            pass
        self.emit('list-changed')

    def _save_state(self):
        dic = Service._save_state(self)
        dic['active'] = self._active
        dic['list'] = {x.title: x.todict() for x in self._list}
        return dic

    def add(self, sample):
        if not [s for s in self._list if s.title == sample.title]:
            self._list.append(sample)
            self._list = sorted(self._list, key=lambda x: x.title)
            self.emit('list-changed')
        else:
            return False
        # if self._active is None:
        #            self._active = sample.title
        #            self.emit('active-changed')
        return True

    def remove(self, sample):
        if isinstance(sample, Sample):
            sample = sample.title
        if not [s for s in self._list if s.title == sample]:
            raise KeyError('Unknown sample with title %s' % sample)
        self._list = [s for s in self._list if s.title != sample]
        if sample == self._active:
            try:
                self._active = self._list[0]
            except IndexError:
                self._active = None
            self.emit('active-changed')
        self.emit('list-changed')

    def set_active(self, sample):
        """sample: string or None"""
        assert (isinstance(sample, str) or (sample is None))
        if sample is None:
            self._active = None
            self.emit('active-changed')
            return
        if isinstance(sample, Sample):
            sample = sample.title
        if [s for s in self._list if s.title == sample]:
            self._active = sample
            self.emit('active-changed')
        else:
            raise SampleStoreError('No sample %s defined.' % sample)

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

    def get_sample(self, title):
        sample = [s for s in self._list if s.title == title]
        if not sample:
            raise KeyError('Unknown sample:', title)
        assert (len(sample) == 1)
        return sample[0]

    def set_sample(self, title, sample):
        self._list = sorted([s for s in self._list if s.title != title] + [sample], key=lambda x: x.title)
        self.emit('list-changed')

    def __contains__(self, item):
        return bool([s for s in self._list if s.title == item])
