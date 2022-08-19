import datetime
import enum
import logging
from typing import Dict, Union, Optional, Tuple, SupportsFloat

import dateutil.parser
import h5py

from .descriptors import LockableFloat, LockableString, LockableOptionalString, LockableDate, LockableEnum, LockState

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FLOATPARAMETER = Union[SupportsFloat, Tuple[SupportsFloat, SupportsFloat]]


class Sample(object):
    class Categories(enum.Enum):
        Calibrant = 'calibration sample'
        NormalizationSample = 'normalization sample'
        Sample = 'sample'
        Sample_and_can = 'sample+can'
        Can = 'can'
        Sample_and_buffer = 'sample+buffer'
        Buffer = 'buffer'
        Simulated_data = 'simulated data'
        Sample_environment = 'sample environment'
        Empty_beam = 'Empty beam'
        Dark = 'Dark'
        None_ = 'none'
        Subtracted = 'subtracted'
        Merged = 'merged'

    class Situations(enum.Enum):
        Air = 'air'
        Vacuum = 'vacuum'
        Sealed_can = 'sealed can'

    title = LockableString('title', 'Untitled')
    positionx = LockableFloat('positionx', 0.0)
    positiony = LockableFloat('positiony', 0.0)
    thickness = LockableFloat('thickness', 0.0)
    transmission = LockableFloat('transmission', 0.0)
    preparedby = LockableString('preparedby', 'Anonymous')
    preparetime = LockableDate('preparetime', None)
    distminus = LockableFloat('distminus', 0.0)
    description = LockableString('description', 'Unknown sample')
    category = LockableEnum('category', Categories, Categories.Sample)
    situation = LockableEnum('situation', Situations, Situations.Vacuum)
    project = LockableOptionalString('project', None)
    maskoverride = LockableOptionalString('maskoverride', None)

    @classmethod
    def fromdict(cls, dic: Dict):
        logger.debug('Sample::fromdict: {}'.format(dic))
        proj = dic.setdefault('project', '__none__')
        proj = None if proj == '__none__' else proj
        maskoverride = dic.setdefault('maskoverride', '__none__')
        maskoverride = None if maskoverride == '__none__' else maskoverride
        obj = cls(
            title=dic['title'],
            positionx=(dic['positionx.val'], dic['positionx.err']),
            positiony=(dic['positiony.val'], dic['positiony.err']),
            thickness=(dic['thickness.val'], dic['thickness.err']),
            transmission=(
                dic['transmission.val'], dic['transmission.err']),
            distminus=(dic['distminus.val'], dic['distminus.err']),
            preparedby=dic['preparedby'],
            preparetime=dateutil.parser.parse(dic['preparetime']).date(),
            description=(dic['description']),
            category=(dic['category']),
            situation=(dic['situation']),
            project=proj,
            maskoverride=maskoverride
        )
        for attribute in ['title', 'positionx', 'positiony', 'thickness', 'transmission', 'distminus', 'preparedby',
                          'preparetime', 'description', 'category', 'situation', 'project', 'maskoverride']:
            setattr(obj, attribute,
                    LockState.LOCKED if dic.setdefault(f'{attribute}.locked', False) else LockState.UNLOCKED)
        return obj

    def todict(self) -> Dict[str, Union[float, str, datetime.datetime, None]]:
        dic = {}
        for floatparam in ['positionx', 'positiony', 'thickness', 'transmission', 'distminus']:
            dic[f'{floatparam}.val'] = getattr(self, floatparam)[0]
            dic[f'{floatparam}.err'] = getattr(self, floatparam)[1]
            dic[f'{floatparam}.locked'] = self.isLocked(floatparam)
        for param in ['title', 'preparedby', 'description', 'project', 'maskoverride']:
            dic[f'{param}'] = getattr(self, param) if getattr(self, param) is not None else '__none__'
            dic[f'{param}.locked'] = self.isLocked(param)
        for param in ['category', 'situation']:
            dic[f'{param}'] = getattr(self, param).value
            dic[f'{param}.locked'] = self.isLocked(param)
        dic['preparetime'] = str(self.preparetime)
        dic['preparetime.locked'] = self.isLocked('preparetime')
        return dic

    def toparam(self) -> str:
        dic = self.todict()
        return '\n'.join(['sample.' + k + ':\t' + str(dic[k]) for k in dic]) + '\n'

    def __init__(self,
                 title: str,
                 positionx: FLOATPARAMETER = 0.0,
                 positiony: FLOATPARAMETER = 0.0,
                 thickness: FLOATPARAMETER = 1.0,
                 transmission: FLOATPARAMETER = 1.0,
                 preparedby: str = 'Anonymous',
                 preparetime: Optional[datetime.date] = None,
                 distminus: FLOATPARAMETER = 0.0,
                 description: str = '',
                 category: Categories = Categories.Sample,
                 situation: Situations = Situations.Vacuum,
                 project: Optional[str] = None,
                 maskoverride: Optional[str] = None):
        self.title = title
        self.positionx = positionx
        self.positiony = positiony
        self.thickness = thickness
        self.transmission = transmission
        self.preparedby = preparedby
        self.category = category
        self.preparetime = preparetime
        self.distminus = distminus
        self.description = description
        self.situation = situation
        self.project = project
        self.maskoverride = maskoverride

    def __repr__(self) -> str:
        return f'Sample({self.title}, ({self.positionx[0]:.3f}, {self.positiony[0]:.3f}), ' \
               f'{self.thickness[0]:.4f}, {self.transmission[0]:.4f})'

    def __str__(self) -> str:
        return f'{self.title} ({self.positionx[0]:.3f}, {self.positiony[0]:.3f}), ' \
               f'{self.thickness[0]:.4f} cm, transm: {self.transmission[0]:.4f}'

    def __eq__(self, other: Union['Sample', str]) -> bool:
        if isinstance(other, self.__class__):
            return self.title == other.title
        elif isinstance(other, str):
            return self.title == other
        else:
            return NotImplemented

    def __ne__(self, other) -> bool:
        return not (self == other)

    def __ge__(self, other) -> bool:
        return self.title >= other.title

    def __gt__(self, other) -> bool:
        return self.title > other.title

    def __lt__(self, other) -> bool:
        return self.title < other.title

    def __le__(self, other) -> bool:
        return self.title <= other.title

    def isLocked(self, attribute: str) -> bool:
        descriptor = type(self).__dict__[attribute]
        return self.__dict__.setdefault(f'_lockable_{attribute}.locked', descriptor.defaultlocked)

    def __copy__(self) -> "Sample":
        return Sample.fromdict(self.todict())

    def toNeXus(self, grp: h5py.Group) -> h5py.Group:
        """Write the NXsample group

        :param grp: the HDF5 to write the NeXus information about this sample to
        :type grp: h5py.Group instance
        :return: the same HDF5 group as `grp`
        :rtype: h5py.Group instance
        """
        grp.attrs['NX_class'] = 'NXsample'
        grp.create_dataset('name', data=self.title)

        grp.create_dataset('type', data=self.category.value)
        grp.create_dataset('situation', data=self.situation.value)
        grp.create_dataset('description', data=self.description)
        grp.create_dataset('preparation_date', data=self.preparetime.isoformat())
        grp.create_dataset('thickness', data=self.thickness[0]).attrs['units'] = 'cm'
        grp.create_dataset('thickness_errors', data=self.thickness[1]).attrs['units'] = 'cm'
        # additionally, path_length and path_length_window could be used, if we know the thickness of the capillary wall
        grp.create_dataset('x_translation', data=self.positionx[0]).attrs['units'] = 'mm'
        grp.create_dataset('y_translation', data=self.positiony[0]).attry['units'] = 'mm'
        grp.create_dataset('x_translation_errors', data=self.positionx[1]).attrs['units'] = 'mm'
        grp.create_dataset('y_translation_errors', data=self.positiony[1]).attry['units'] = 'mm'
        # The NXsample base class specifies that the transmission should be a NXdata. A little overkill in our case,
        # but let's conform to the standards...
        transmgrp = grp.create_group('transmission')
        transmgrp.attrs.update({'NX_class': 'NXdata', 'signal': 'data'})
        transmgrp.create_dataset('data', data=[self.transmission[0]])
        transmgrp.create_dataset('errors', data=[self.transmission[1]])
        return grp
