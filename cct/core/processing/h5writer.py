"""A separate process for writing HDF5 files

"""

import multiprocessing
import queue
from typing import List, Any, Dict, Optional

import h5py
import numpy as np


class InMessage:
    def __init__(self, index:int, grppath:List[str], datasetname:str, datasetvalue:Optional[np.ndarray]=None, attrs:Optional[Dict[str, Any]]=None, updateattrs:bool=True):
        self.index=index
        self.grppath=grppath
        self.datasetname=datasetname
        self.datasetvalue=datasetvalue
        self.attrs = attrs
        self.updateattrs = updateattrs

class OutMessage:
    def __init__(self, index:int, type_:str, args:[]):
        self.index=index
        self.type_=type_
        self.args=args

class H5Writer(multiprocessing.Process):
    def __init__(self, h5filename):
        super().__init__()
        self.queue=multiprocessing.Queue()
        self.replyqueue=multiprocessing.Queue()
        self.h5filename = h5filename
        self.outstanding=[]
        self.lastindex=0

    def write(self, grppath:List[str], datasetname:Optional[str], datasetvalue:Optional[np.ndarray]=None, attrs:Optional[Dict[str, Any]]=None, updateattrs:bool=True):
        """Write to the HDF5 file. This is a multi-purpose function, performing the
            following tasks:

        1. Creating a group hierarchy: all elements of `grppath` will be ensured to be
            present in the HDF5 hierarchy.
        2. Creating/modifying a new dataset: if neither `datasetname` nor `datasetvalue`
            are None, the respective HDF5 dataset will be created/modified in the group
            pointed to by `grppath`.
        3. Setting attributes to a datasets (if `datasetname` is not None) or a group
            (if `datasetname` is None), if `attrs` is not None. The behaviour is controlled
            by the `updateattrs`: if True, attributes are only added/modified. If False,
            the complete attribute dictionary is replaced.

        The actual I/O is carried out by a separate process, so the completion of this
        function does not ensure the completion of the I/O.

        :param grppath: group path, i.e. a list of group names in the hdf5 hierarchy.
            Nonexistent groups will be created. This list must not contain dataset
            names.
        :type grppath: list of str
        :param datasetname: the name of the dataset to be manipulated
        :type datasetname: str or None
        :param datasetvalue: the new value of the dataset
        :type datasetvalue: numpy ndarray
        :param attrs: attributes to be applied on the dataset or the group
        :type attrs: dictionary
        :param updateattrs: True if the attributes should be updated and False if clobbered
        :type updateattrs: bool
        """
        self.fetchResults()
        self.lastindex+=1
        self.queue.put_nowait(InMessage(self.lastindex, grppath, datasetname, datasetvalue, attrs, updateattrs))
        self.outstanding.append(self.lastindex)

    def fetchResults(self):
        while True:
            try:
                message = self.replyqueue.get_nowait()
                assert isinstance(message, OutMessage)
                self.outstanding.remove(message.index)
                if message.type_=='exception':
                    raise message.args[0]
            except queue.Empty:
                return

    def run(self) -> None:
        while True:
            message = self.queue.get(block=True)
            if (message.index == 0) and (message.datasetname=='') and (message.datasetvalue is None) and (message.attrs is None):
                # NOP = exit
                break
            assert isinstance(message, InMessage)
            try:
                with h5py.File(self.h5filename, 'a') as h5:
                    grp=h5
                    for gname in message.grppath:
                        try:
                            grp=grp[gname]
                        except KeyError:
                            grp=grp.create_group(gname)
                    if message.datasetvalue is not None:
                        # the dataset must be removed and re-created
                        del grp[message.datasetname]
                        grp.create_dataset(message.datasetname, data=message.datasetvalue)
                    if message.attrs is not None:
                        # attributes must be written
                        if message.datasetname is None:
                            # write attributes to the group.
                            attrbase = grp
                        else:
                            attrbase = grp[message.datasetname]
                        if message.updateattrs:
                            for a in message.attrs:
                                attrbase.attrs[a]=message.attrs[a]
                        else:
                            attrbase.attrs=message.attrs
                    self.replyqueue.put_nowait(OutMessage(message.index, 'done', []))
            except Exception as exc:
                self.replyqueue.put_nowait(OutMessage(message.index, 'exception', [exc]))

    def join(self, timeout: Optional[float] = None) -> None:
        self.queue.put_nowait(InMessage(0,[], '', None, None, True))
        return super().join(timeout)