import logging
from typing import Optional, Union, Dict

from .service import Service, ServiceError
from ..instrument.sample import Sample
from ..utils.callback import SignalFlags

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SampleStoreError(ServiceError):
    pass


class SampleStore(Service):
    __signals__ = {'list-changed': (SignalFlags.RUN_FIRST, None, ()),
                   'active-changed': (SignalFlags.RUN_FIRST, None, ()),
                   }

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
