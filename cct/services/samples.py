from .service import Service, ServiceError
from ..instrument.sample import Sample


class SampleStoreError(ServiceError):
    pass


class SampleStore(Service):

    def __init__(self, *args, **kwargs):
        Service.__init(self, *args, **kwargs)
        self._list = []
        self._active = None

    def _load_state(self, dictionary):
        Service._load_state(self, dictionary)
        self._list = [Sample.fromdict(sampledict)
                      for sampledict in dictionary['list']]
        self._active = dictionary['active']

    def _save_state(self):
        dic = Service._save_state(self)
        dic['active'] = self._active
        dic['list'] = self._list[:]
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
        return self._list[self._active]
