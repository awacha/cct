"""Keep track of file sequence numbers and do other filesystem-related jobs"""
import datetime
import errno
import logging
import math
import os
import pickle
import re
import time
from typing import Optional, Dict, Sequence

import dateutil.parser
import numpy as np
from sastool.io.credo_cct import Exposure, Header
from sastool.io.twodim import readcbf
from sastool.misc.errorvalue import ErrorValue
from scipy.io import loadmat

from .service import Service, ServiceError
from ..utils.callback import SignalFlags
from ..utils.pathutils import find_in_subfolders, find_subfolders

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

"""Default path settings in working directory:

- config
- images
   - cbf
   - scn
   - tst
   - tra
   - <anything else, without '.' in the name, just one level>
- param
   - cbf
   - scn
   - tst
   - tra
   - <anything else, without '.' in the name, just one level>
- eval1d
- eval2d
- scan
- param_override
- log

"""


class FileSequenceError(ServiceError):
    pass


class FileSequence(Service):
    """A class to keep track on file sequence numbers and folders,
    as well as do some I/O related tasks.
    """
    name = 'filesequence'

    __signals__ = {'nextfsn-changed': (SignalFlags.RUN_FIRST, None, (str, int,)),
                   'nextscan-changed': (SignalFlags.RUN_FIRST, None, (int,)),
                   'lastfsn-changed': (SignalFlags.RUN_FIRST, None, (str, int,)),
                   'lastscan-changed': (SignalFlags.RUN_FIRST, None, (int,))}

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._lastfsn = {}
        self._lastscan = 0
        self._nextfreescan = 0
        self._nextfreefsn = {}
        self.scanfile_toc = {}
        self._running_scan = None
        self._masks = {}
        self._scanfile = os.path.join(
            self.instrument.config['path']['directories']['scan'],
            self.instrument.config['scan']['scanfile'])
        self.init_scanfile()
        self.reload()

    def init_scanfile(self):
        """Initialize the scanfile."""

        if not os.path.exists(self._scanfile):
            with open(self._scanfile, 'wt', encoding='utf-8') as f:
                f.write('#F ' + os.path.abspath(self._scanfile) + '\n')
                f.write('#E {}\n'.format(time.time()))
                f.write('#D {}\n'.format(time.asctime()))
                f.write('#C CREDO scan file\n')
                f.write('#O0 ' + '  '.join(sorted([m['name'] for m in
                                                   self.instrument.config['motors'].values()])) + '\n')
                f.write('\n')

    # noinspection PyPep8Naming
    def new_scan(self, cmdline: str, comment: str, exptime: float, N: int, motorname: str) -> int:
        """Prepare a new scan measurement. To be called when a start
        measurement is commenced.

        The main task of this method is to write the header of the next scan
        in the scan file. This method also acquires a next scan number, which
        is returned."""
        if self._running_scan is not None:
            raise FileSequenceError('Cannot start scan: scan #{:d} already running.'.format(self._running_scan))
        scanidx = self.get_nextfreescan(acquire=True)
        with open(self._scanfile, 'at', encoding='utf-8') as f:
            self.scanfile_toc[self._scanfile][scanidx] = {'pos': f.tell() + 1, 'cmd': cmdline,
                                                          'date': datetime.datetime.now(), 'comment': comment}
            f.write('\n#S {:d}  {}\n'.format(scanidx, cmdline))
            f.write('#D {}\n'.format(time.asctime()))
            f.write('#C {}\n'.format(comment))
            f.write('#T {:f}  (Seconds)\n'.format(exptime))
            f.write('#G0 0\n')
            f.write('#G1 0\n')
            f.write('#Q 0 0 0\n')
            # write the motor positions. Each line starts with a '#P<idx>',
            # where <idx> starts from zero. Then the motor positions at the
            # beginning ensue, in the same order as they are in the '#O'
            # section of the SPEC file header. Each line should contain at
            # most 8 numbers.
            for i in range(math.ceil(len(self.instrument.motors) / 8)):
                f.write('#P{:d} '.format(i))
                f.write(' '.join(['{:f}'.format(
                    self.instrument.motors[m].where())
                    for m in sorted(self.instrument.motors)]))
                f.write('\n')
            f.write('#N {:d}\n'.format(N))  # the number of scan points
            f.write('#L ' + '  '.join([motorname] +
                                      self.instrument.config['scan']['columns']) + '\n')
        logger.debug('Written entry for scan {:d} into scanfile {}'.format(
            scanidx, self._scanfile))
        self._running_scan = scanidx
        return scanidx

    def scan_done(self, scannumber: int):
        """Called when a scan measurement finishes.

        Responsible for emitting the lastscan-changed signal."""
        if self._running_scan is None:
            raise FileSequenceError('Cannot end scan: no scan running.')
        self._lastscan = max(self._lastscan, scannumber)
        self._running_scan = None
        self.emit('lastscan-changed', self._lastscan)

    def load_scanfile_toc(self, scanfile: Optional[str] = None) -> Dict:
        if scanfile is None:
            scanfile = self._scanfile
        with open(scanfile, 'rt', encoding='utf-8') as f:
            self.scanfile_toc[scanfile] = {}
            l = f.readline()
            idx = None
            while l:  # `l` will be readline-d. When the file ends, `l==''`.
                l = l.strip()  # just for convenience.
                if l.startswith('#S'):
                    # calculate the position just before the '#' of this line.
                    pos = f.tell() - len(l) - 1
                    start, idx, cmd = l.split(None, 2)
                    idx = int(idx)
                    self.scanfile_toc[scanfile][idx] = {'pos': pos, 'cmd': cmd}
                elif l.startswith('#D') and idx is not None:
                    # idx can be None if we are in the file header part, before
                    # the first scan.
                    self.scanfile_toc[scanfile][idx]['date'] = dateutil.parser.parse(l.split(None, 1)[1])
                elif l.startswith('#C') and idx is not None:
                    try:
                        self.scanfile_toc[scanfile][idx]['comment'] = l.split(None, 1)[1]
                    except IndexError:
                        self.scanfile_toc[scanfile][idx]['comment'] = 'no comment'
                l = f.readline()
        return self.scanfile_toc[scanfile]

    def load_scan(self, index: int, scanfile: Optional[str] = None):
        """Load a scan with `index` from `scanfile`. If `scanfile` is None,
        the default scanfile is used.

        Since scan files are text-based SPEC files and can hold many scans,
        a table-of-contents dictionary is kept in self.scanfile_toc for
        each scanfile.
        """
        if scanfile is None:
            scanfile = self._scanfile
        assert isinstance(scanfile, str)
        if scanfile not in self.scanfile_toc:
            self.load_scanfile_toc(scanfile)
        result = {}
        with open(scanfile, 'rt', encoding='utf-8') as f:
            f.seek(self.scanfile_toc[scanfile][index]['pos'], 0)
            l = f.readline().strip()
            if not l.startswith('#S {:d}'.format(index)):
                raise FileSequenceError('Error in scan file: line expected to contain "#S {:d}"'.format(index))
            length = None
            index = None
            while l:  # scan ends with an empty line.
                if l.startswith('#S'):
                    result['index'] = int(l.split()[1])
                    result['command'] = l.split(None, 2)[2]
                elif l.startswith('#D'):
                    result['date'] = dateutil.parser.parse(l[3:])
                elif l.startswith('#C'):
                    result['comment'] = l[3:]
                elif l.startswith('#T') and l.endswith('(Seconds)'):
                    result['countingtime'] = float(l.split()[1])
                elif l.startswith('#P'):
                    if 'positions' not in result:
                        result['positions'] = []
                    result['positions'].append([float(x) for x in l.split()[1:]])
                elif l.startswith('#N'):
                    length = int(l[3:])
                elif l.startswith('#L'):
                    result['signals'] = l[3:].split('  ')
                    if length is None:
                        raise FileSequenceError(
                            'Encountered a line starting with "#L" before reading a line starting with "#N"')
                    result['data'] = np.zeros(length,
                                              dtype=list(zip(result['signals'], [np.float] * len(result['signals']))))
                    index = 0
                elif l.startswith('#'):
                    pass
                else:
                    logger.debug('Signals: (' + ', '.join(result['signals']) + ')')
                    logger.debug('l.split(): ')
                    result['data'][index] = tuple(float(x) for x in l.split())
                    index += 1
                # strip the '\n' character from the end. This is essential for
                #  the correct termination of this loop.
                l = f.readline().strip()
            if 'data' in result:
                result['data'] = result['data'][:index]
        return result

    def get_scans(self, scanfile: Optional[str] = None):
        """Get a list of scans in the scanfile."""
        if scanfile is None:
            scanfile = self._scanfile
        assert isinstance(scanfile, str)
        return self.scanfile_toc[scanfile]

    def get_scanfiles(self):
        """Get a list of indexed scanfiles"""
        return sorted(self.scanfile_toc.keys())

    def reload(self):
        """Check the well-known directories and their subfolders for sequential files.

        A sequential file here means a file whose name follows the <prefix>_<fsn>.<extension>
        scheme.
        """
        # check raw detector images
        for subdir, extension in [('images', 'cbf'), ('param', 'param'),
                                  ('param_override', 'param'),
                                  ('eval2d', 'npz'), ('eval1d', 'txt')]:
            # find all subdirectories in `directory`, including `directory`
            # itself
            directory = self.instrument.config['path']['directories'][subdir]
            logger.debug('Looking in directory ' + directory)
            filename_regex = re.compile(r'^(?P<prefix>\w+)_(?P<fsn>\d+)\.' + extension + '$')
            for d in [directory] + find_subfolders(directory):
                # find all files
                matchlist = [m for m in [filename_regex.match(f) for f in os.listdir(d)] if m is not None]
                # find all file prefixes, like 'crd', 'tst', 'tra', 'scn', etc.
                for prefix in {m.group('prefix') for m in matchlist}:
                    logger.debug('Treating prefix ' + prefix)
                    if prefix not in self._lastfsn:
                        logger.debug('We haven\'t seen this prefix yet.')
                        self._lastfsn[prefix] = 0
                        self.emit('lastfsn-changed', prefix, self._lastfsn[prefix])
                    # find the highest available FSN of the current prefix in
                    # this directory
                    maxfsn = max([int(m.group('fsn')) for m in matchlist if m.group('prefix') == prefix])
                    logger.debug('Maxfsn for prefix {} in this directory: {:d}'.format(prefix, maxfsn))
                    if maxfsn > self._lastfsn[prefix]:
                        logger.debug('Updating maxfsn.')
                        self._lastfsn[prefix] = maxfsn
                        self.emit('lastfsn-changed', prefix, self._lastfsn[prefix])

        # add known prefixes to self._lastfsn if they were not yet added.
        for prefix in self.instrument.config['path']['prefixes'].values():
            if prefix not in self._lastfsn:
                logger.debug('Adding not found prefix to _lastfsn: ' + prefix)
                self._lastfsn[prefix] = 0

        # update self._nextfreefsn
        for prefix in self._lastfsn:
            if prefix not in self._nextfreefsn:
                logger.debug('Initializing nextfreefsn for prefix ' + prefix)
                self._nextfreefsn[prefix] = 0
            if self._nextfreefsn[prefix] < self._lastfsn[prefix]:
                logger.debug(
                    'Updating nextfreefsn for prefix {} from {:d} to {:d}'.format(prefix, self._nextfreefsn[prefix],
                                                                                  self._lastfsn[prefix]))
                self._nextfreefsn[prefix] = self._lastfsn[prefix] + 1
                self.emit('nextfsn-changed', prefix, self._nextfreefsn[prefix])

        # reload scan file table of contents.
        scanpath = self.instrument.config['path']['directories']['scan']
        for subdir in [scanpath] + find_subfolders(scanpath):
            for scanfile in [f for f in os.listdir(subdir)
                             if f.endswith('.spec')]:
                scanfile = os.path.join(subdir, scanfile)
                self.load_scanfile_toc(scanfile)

        lastscan = max([max([k for k in self.scanfile_toc[sf]] + [0])
                        for sf in self.scanfile_toc] + [0])
        if self._lastscan != lastscan:
            self._lastscan = lastscan
            self.emit('lastscan-changed', self._lastscan)

            #       logger.debug('Max. scan index: {:d}'.format(self._lastscan))
        if self._nextfreescan < self._lastscan + 1:
            self._nextfreescan = self._lastscan + 1
            self.emit('nextscan-changed', self._nextfreescan)

    def get_lastfsn(self, prefix: str):
        return self._lastfsn[prefix]

    def get_lastscan(self):
        return self._lastscan

    def get_nextfreescan(self, acquire: bool = True):
        try:
            return self._nextfreescan
        finally:
            if acquire:
                self._nextfreescan += 1
                self.emit('nextscan-changed', self._nextfreescan)

    def get_nextfreefsn(self, prefix: str, acquire: bool = True):
        if prefix not in self._nextfreefsn:
            self._nextfreefsn[prefix] = 1
        try:
            return self._nextfreefsn[prefix]
        finally:
            if acquire:
                self._nextfreefsn[prefix] += 1
                self.emit('nextfsn-changed', prefix, self._nextfreefsn[prefix])

    # noinspection PyPep8Naming
    def get_nextfreefsns(self, prefix: str, N: int, acquire: bool = True):
        if N <= 0:
            raise FileSequenceError("Number of FSNs to allocate must be a positive integer")
        if prefix not in self._nextfreefsn:
            self._nextfreefsn[prefix] = 1
        try:
            return range(self._nextfreefsn[prefix],
                         self._nextfreefsn[prefix] + N)
        finally:
            if acquire:
                self._nextfreefsn[prefix] += N
            self.emit('nextfsn-changed', prefix, self._nextfreefsn[prefix])

    def new_exposure(self, fsn: int, filename: str, prefix: str, startdate: datetime.datetime,
                     **kwargs):
        """Called by various parts of the instrument if a new exposure file
        has became available

        Keyword arguments can be given: they will be passed on to the submit()
        method of the exposureanalyzer service.
        """
        if (prefix not in self._lastfsn) or (fsn > self._lastfsn[prefix]):
            self._lastfsn[prefix] = fsn
            self.emit('lastfsn-changed', prefix, self._lastfsn[prefix])
        logger.debug('New exposure: {} (fsn: {:d}, prefix: {})'.format(filename, fsn, prefix))
        try:
            # try to remove the leading part of filenames like '/disk2/images/scn/scn_12034.cbf'
            filename = filename[filename.index('images') + 7:]
        except (IndexError, ValueError):
            pass
        # write header file if needed
        config = self.instrument.config

        if prefix in [config['path']['prefixes']['scn'],
                      config['path']['prefixes']['tra']]:
            simpleparams = True
        else:
            simpleparams = False

        params = self.construct_params(prefix, fsn, startdate, simpleparams)
        picklefilename = params['filename']
        # save the params dictionary
        with open(picklefilename, 'wb') as f:
            logger.debug('Dumping pickle file ' + picklefilename)
            pickle.dump(params, f)
        kwargs['param'] = params
        self.instrument.services['exposureanalyzer'].submit(
            fsn, filename, prefix, **kwargs)

    def construct_params(self, prefix, fsn, startdate, simple=False):
        # construct the params dictionary
        config = self.instrument.config
        params = {}
        picklefilename = os.path.join(
            self.instrument.config['path']['directories']['param'],
            self.exposurefileformat(prefix, fsn) + '.pickle')
        params['fsn'] = fsn
        params['filename'] = os.path.abspath(picklefilename)
        params['exposure'] = {'fsn': fsn,
                              'exptime': self.instrument.get_device('detector').get_variable('exptime'),
                              'monitor': self.instrument.get_device('detector').get_variable('exptime'),
                              'startdate': str(startdate),
                              'date': str(datetime.datetime.now()),
                              'enddate': str(datetime.datetime.now())}
        params['geometry'] = {}
        for k in config['geometry']:
            params['geometry'][k] = config['geometry'][k]
        dist = ErrorValue(config['geometry']['dist_sample_det'],
                          config['geometry']['dist_sample_det.err'])
        if not simple:
            sample = self.instrument.services['samplestore'].get_active()
        else:
            sample = None
        if sample is not None:
            distcalib = dist - sample.distminus
            params['sample'] = sample.todict()
        else:
            sampledict = self.instrument.services['samplestore'].get_samples()[0].todict()
            for v in sampledict:
                if isinstance(sampledict[v], str):
                    sampledict[v] = '---'
                elif isinstance(sampledict[v], (float, int)):
                    sampledict[v] = 0
                elif isinstance(sampledict[v], ErrorValue):
                    sampledict[v] = ErrorValue(0, 0)
                else:
                    sampledict[v] = None
            params['sample'] = sampledict
            distcalib = dist
        params['geometry']['truedistance'] = distcalib.val
        params['geometry']['truedistance.err'] = distcalib.err
        if not simple:
            params['motors'] = {}
            for m in sorted(self.instrument.motors):
                params['motors'][m] = self.instrument.motors[m].where()
            params['devices'] = {}
            for d in sorted(self.instrument.devices):
                params['devices'][d] = {}
                for v in sorted(self.instrument.devices[d].list_variables()):
                    params['devices'][d][v] = self.instrument.devices[d].get_variable(v)
            params['environment'] = {}
            try:
                params['environment']['vacuum_pressure'] = self.instrument.get_device('vacuum').get_variable('pressure')
            except KeyError:
                pass
            try:
                tempdev = self.instrument.get_device('temperature')
            except KeyError:
                pass
            else:
                try:
                    params['environment']['temperature_setpoint'] = tempdev.get_variable('setpoint')
                except KeyError as ke:
                    logger.warning('Cannot write property: ' + str(ke.args[0]))
                try:
                    params['environment']['temperature'] = tempdev.get_variable('temperature_internal')
                except KeyError as ke:
                    logger.warning('Cannot write property: ' + str(ke.args[0]))
            params['accounting'] = {}
            for k in config['services']['accounting']:
                params['accounting'][k] = config['services']['accounting'][k]

        return params

    def get_prefixes(self):
        """Return the known prefixes"""
        return list(self._lastfsn.keys())

    def is_cbf_ready(self, filename: str):
        """Check if a CBF file made by the detector is available."""
        logger.debug('Checking if file {} is available'.format(filename))
        imgdir = self.instrument.config['path']['directories']['images']
        os.stat(self.instrument.config['path']['directories']['images'])
        try:
            logger.debug('Checking in directory {}'.format(imgdir))
            os.stat(os.path.join(imgdir, filename))
            logger.debug('File found!')
            return True
        except FileNotFoundError:
            pass
        pattern = '(?P<prefix>\w{{3}})_(?P<fsn>\d{{{}}})\.cbf'.format(self.instrument.config['path']['fsndigits'])
        logger.debug('Trying to match {} against {}'.format(filename, pattern))
        m = re.match(pattern, filename)
        if m is not None:
            logger.debug(
                'Not found, but we have a prefix {0}: checking in directory {1}/{0}'.format(m.group('prefix'), imgdir))
            try:
                os.stat(os.path.join(imgdir, m.group('prefix'), filename))
                logger.debug('File found')
                return True
            except FileNotFoundError:
                logger.debug('File not found!')
                return False
        logger.debug('File not found')
        return False

    def exposurefileformat(self, prefix: str, fsn: Optional[int] = None):
        if fsn is None:
            return '{prefix}_{{:0{fsndigits:d}d}}'.format(
                prefix=prefix,
                fsndigits=self.instrument.config['path']['fsndigits'])
        else:
            return '{prefix}_{fsn:0{fsndigits:d}d}'.format(
                prefix=prefix,
                fsndigits=self.instrument.config['path']['fsndigits'],
                fsn=fsn)

    def load_cbf(self, prefix: str, fsn: int):
        """Load the CBF file."""
        cbfbasename = self.exposurefileformat(prefix, fsn) + '.cbf'
        for subpath in [prefix, '']:
            cbfname = os.path.join(
                self.instrument.config['path']['directories']['images'],
                subpath, cbfbasename)
            try:
                return readcbf(cbfname)[0]
            except FileNotFoundError:
                pass
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), cbfbasename)

    def load_header(self, prefix: str, fsn: int) -> Header:
        filebasename = self.exposurefileformat(prefix, fsn) + '.pickle'
        for path in [
            self.instrument.config['path']['directories']['param_override'],
            self.instrument.config['path']['directories']['param']
        ]:
            try:
                header = Header.new_from_file(os.path.join(path, filebasename))
                if path == self.instrument.config['path']['directories']['param_override']:
                    logger.debug(
                        'Using parameter override for prefix {} fsn {}. S-D: {}'.format(prefix, fsn, header.distance))
                return header
            except FileNotFoundError:
                continue
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), filebasename)

    def load_exposure(self, prefix: str, fsn: int) -> Exposure:
        header = self.load_header(prefix, fsn)
        cbfbasename = self.exposurefileformat(prefix, fsn) + '.cbf'
        imgpath = self.instrument.config['path']['directories']['images']
        for path in [os.path.join(imgpath, prefix), imgpath]:
            try:
                return Exposure.new_from_file(
                    os.path.join(path, cbfbasename), header,
                    self.get_mask(header.maskname))
            except FileNotFoundError:
                continue
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), cbfbasename)

    def load_param(self, prefix: str, fsn: int) -> Dict:
        picklebasename = self.exposurefileformat(prefix, fsn) + '.pickle'
        for path in [
            self.instrument.config['path']['directories']['param_override'],
            self.instrument.config['path']['directories']['param']
        ]:
            try:
                picklename = os.path.join(
                    path, picklebasename)
                with open(picklename, 'rb') as f:
                    return pickle.load(f)
            except FileNotFoundError:
                continue
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), picklebasename)

    def get_mask(self, maskname: str) -> np.ndarray:
        if ((maskname not in self._masks) or
                (os.stat(self._masks[maskname]['path']).st_atime > self._masks[maskname]['atime'])):
            # if this mask has not yet been loaded or it has changed on the disk, load it.
            if not os.path.isabs(maskname):
                # find the absolute path.
                filename = find_in_subfolders(self.instrument.config['path']['directories']['mask'],
                                              maskname)
            else:
                filename = maskname
            m = loadmat(filename)
            self._masks[maskname] = {'path': filename,
                                     'atime': os.stat(filename).st_atime,
                                     'mask': m[[k for k in m.keys() if not k.startswith('__')][0]].view(bool)}
        return self._masks[maskname]['mask']

    def get_mask_filepath(self, maskname: str) -> str:
        mask = self.get_mask(maskname)
        return self._masks[maskname]['path']

    def get_scanfile(self) -> str:
        return self._scanfile

    def write_scandataline(self, position: float, counters: Sequence[float]):
        if self._running_scan is None:
            raise FileSequenceError('Cannot append to scanfile: no scan running.')
        with open(self._scanfile, 'at', encoding='utf-8') as f:
            f.write(' '.join([str(c) for c in counters]) + '\n')
