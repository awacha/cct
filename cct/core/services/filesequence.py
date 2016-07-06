"""Keep track of file sequence numbers and do other filesystem-related jobs"""
import datetime
import logging
import os
import pickle
import re
import time
from typing import Optional, Tuple

import dateutil.parser
import numpy as np
from gi.repository import GObject
from sastool.io.twodim import readcbf
from scipy.io import loadmat

from .service import Service, ServiceError
from ..utils.errorvalue import ErrorValue
from ..utils.io import write_legacy_paramfile
from ..utils.pathutils import find_in_subfolders, find_subfolders
from ..utils.sasimage import SASImage

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
    """A class to keep track on file sequence numbers and folders"""
    name = 'filesequence'

    __gsignals__ = {'nextfsn-changed': (GObject.SignalFlags.RUN_FIRST, None, (str, int,)),
                    'nextscan-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
                    'lastfsn-changed': (GObject.SignalFlags.RUN_FIRST, None, (str, int,)),
                    'lastscan-changed': (GObject.SignalFlags.RUN_FIRST, None, (int,))}

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._lastfsn = {}
        self._lastscan = 0
        self._nextfreefsn = {}
        self._scanfile_toc = {}
        self.init_scanfile()
        self.reload()

    def init_scanfile(self):
        self._scanfile = os.path.join(
            self.instrument.config['path']['directories']['scan'],
            self.instrument.config['scan']['scanfile'])

        if not os.path.exists(self._scanfile):
            with open(self._scanfile, 'wt', encoding='utf-8') as f:
                f.write('#F ' + os.path.abspath(self._scanfile) + '\n')
                f.write('#E {}\n'.format(time.time()))
                f.write('#D {}\n'.format(time.asctime()))
                f.write('#C CREDO scan file\n')
                f.write('#O0 ' + '  '.join(sorted([m['name'] for m in
                                                   self.instrument.config['motors']],
                                                  key=lambda x: x['name'])) + '\n')
                f.write('\n')

    def new_scan(self, cmdline: str, comment: str, exptime: float, N: int, motorname: str):
        scanidx = self.get_nextfreescan(acquire=True)
        with open(self._scanfile, 'at', encoding='utf-8') as f:
            self._scanfile_toc[self._scanfile][scanidx] = {'pos': f.tell() + 1, 'cmd': cmdline,
                                                           'date': datetime.datetime.now()}
            f.write('\n#S {:d}  {}\n'.format(scanidx, cmdline))
            f.write('#D {}\n'.format(time.asctime()))
            f.write('#C {}\n'.format(comment))
            f.write('#T {:f}  (Seconds)\n'.format(exptime))
            f.write('#G0 0\n')
            f.write('#G1 0\n')
            f.write('#Q 0 0 0')
            entry_index = 8
            p_index = -1
            for m in sorted(self.instrument.motors):
                if entry_index >= 8:
                    p_index += 1
                    f.write('\n#P{:d}'.format(p_index))
                    entry_index = 0
                f.write(' {:f}'.format(self.instrument.motors[m].where()))
                entry_index += 1
            f.write('\n#N {:d}\n'.format(N))
            f.write('#L ' + '  '.join([motorname] + self.instrument.config['scan']['columns']) + '\n')
        logger.info('Written entry for scan {:d} into scanfile {}'.format(scanidx, self._scanfile))
        return scanidx

    def scan_done(self, scannumber: int):
        self._lastscan = max(self._lastscan, scannumber)
        self.emit('lastscan-changed', self._lastscan)

    def load_scan(self, index: int, scanfile: Optional[str] = None):
        if scanfile is None:
            scanfile = self._scanfile
        result = {}
        with open(scanfile, 'rt', encoding='utf-8') as f:
            f.seek(self._scanfile_toc[scanfile][index]['pos'], 0)
            l = f.readline().strip()
            if not l.startswith('#S'):
                raise FileSequenceError('Error in scan file: line expected to start with "#S"')
            if int(l.split()[1]) != index:
                raise FileSequenceError('Error in scan file: line expected to contain "#S {:d}"'.format(index))
            length = None
            index = None
            while l:
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
                    result['data'][index] = tuple(float(x) for x in l.split())
                    index += 1
                l = f.readline().strip()
            if 'data' in result:
                result['data'] = result['data'][:index]
        return result

    def get_scans(self, scanfile: str):
        return self._scanfile_toc[scanfile]

    def get_scanfiles(self):
        return sorted(self._scanfile_toc.keys())

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

        # reload scans
        scanpath = self.instrument.config['path']['directories']['scan']
        for subdir in [scanpath] + find_subfolders(scanpath):
            for scanfile in [f for f in os.listdir(subdir)
                             if f.endswith('.spec')]:
                scanfile = os.path.join(subdir, scanfile)
                with open(scanfile, 'rt', encoding='utf-8') as f:
                    self._scanfile_toc[scanfile] = {}
                    l = f.readline()
                    idx = None
                    while l:
                        l = l.strip()
                        if l.startswith('#S'):
                            pos = f.tell() - len(l) - 1
                            start, idx, cmd = l.split(None, 2)
                            idx = int(idx)
                            self._scanfile_toc[scanfile][idx] = {'pos': pos, 'cmd': cmd}
                        elif l.startswith('#D') and idx is not None:
                            self._scanfile_toc[scanfile][idx]['date'] = dateutil.parser.parse(l.split(None, 1)[1])
                        elif l.startswith('#C') and idx is not None:
                            try:
                                self._scanfile_toc[scanfile][idx]['comment'] = l.split(None, 1)[1]
                            except IndexError:
                                self._scanfile_toc[scanfile][idx]['comment'] = 'no comment'
                        l = f.readline()
                        #        for sf in self._scanfile_toc:
                        #            logger.debug('Max. scan index in file {}: {:d}'.format(sf, max([k for k in self._scanfile_toc[sf]]+[0])))

        lastscan = max([max([k for k in self._scanfile_toc[sf]] + [0])
                        for sf in self._scanfile_toc] + [0])
        if self._lastscan != lastscan:
            self._lastscan = lastscan
            self.emit('lastscan-changed', self._lastscan)

            #       logger.debug('Max. scan index: {:d}'.format(self._lastscan))
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
                     argstuple: Optional[Tuple] = None):
        """Called by various parts of the instrument if a new exposure file
        has became available"""
        if argstuple is None:
            argstuple = ()
        if (prefix not in self._lastfsn) or (fsn > self._lastfsn[prefix]):
            self._lastfsn[prefix] = fsn
            self.emit('lastfsn-changed', prefix, self._lastfsn[prefix])
        logger.debug('New exposure: {} (fsn: {:d}, prefix: {})'.format(filename, fsn, prefix))
        filename = filename[filename.index('images') + 7:]
        # write header file if needed
        config = self.instrument.config
        if prefix in [config['path']['prefixes']['crd'],
                      config['path']['prefixes']['tst']]:

            # construct the params dictionary
            params = {}
            paramfilename = os.path.join(
                self.instrument.config['path']['directories']['param'],
                '{prefix}_{fsn:0{fsndigits:d}d}.param'.format(
                    prefix=prefix, fsndigits=config['path']['fsndigits'], fsn=fsn))
            picklefilename = paramfilename[:-len('.param')] + '.pickle'
            sample = self.instrument.samplestore.get_active()
            params['fsn'] = fsn
            params['filename'] = os.path.abspath(picklefilename)
            params['exposure'] = {'fsn': fsn,
                                  'exptime': self.instrument.detector.get_variable('exptime'),
                                  'monitor': self.instrument.detector.get_variable('exptime'),
                                  'startdate': str(startdate),
                                  'date': str(datetime.datetime.now()),
                                  'enddate': str(datetime.datetime.now())}
            params['geometry'] = {}
            for k in config['geometry']:
                params['geometry'][k] = config['geometry'][k]
            dist = ErrorValue(config['geometry']['dist_sample_det'],
                              config['geometry']['dist_sample_det.err'])
            if sample is not None:
                distcalib = dist - sample.distminus
                params['sample'] = sample.todict()
            else:
                distcalib = dist
            params['geometry']['truedistance'] = distcalib.val
            params['geometry']['truedistance.err'] = distcalib.err

            params['motors'] = {}
            for m in sorted(self.instrument.motors):
                params['motors'][m] = self.instrument.motors[m].where()
            params['devices'] = {}
            for d in sorted(self.instrument.devices):
                params['devices'][d] = {}
                for v in sorted(self.instrument.devices[d].list_variables()):
                    params['devices'][d][v] = self.instrument.devices[d].get_variable(v)

            params['environment'] = {}
            if 'vacuum' in self.instrument.environmentcontrollers:
                params['environment']['vacuum_pressure'] = self.instrument.environmentcontrollers[
                    'vacuum'].get_variable('pressure')
            if 'temperature' in self.instrument.environmentcontrollers:
                try:
                    params['environment']['temperature_setpoint'] = self.instrument.environmentcontrollers[
                        'temperature'].get_variable('setpoint')
                except KeyError as ke:
                    logger.warning('Cannot write property: ' + str(ke.args[0]))
                try:
                    params['environment']['temperature'] = self.instrument.environmentcontrollers[
                        'temperature'].get_variable('temperature_internal')
                except KeyError as ke:
                    logger.warning('Cannot write property: ' + str(ke.args[0]))
            params['accounting'] = {}
            for k in config['services']['accounting']:
                params['accounting'][k] = config['services']['accounting'][k]

            # save the params dictionary
            with open(picklefilename, 'wb') as f:
                logger.debug('Dumping pickle file ' + picklefilename)
                pickle.dump(params, f)

            write_legacy_paramfile(paramfilename, params)
            argstuple = argstuple + (params,)
        self.instrument.exposureanalyzer.submit(
            fsn, filename, prefix, argstuple)

    def get_prefixes(self):
        """Return the known prefixes"""
        return list(self._lastfsn.keys())

    def is_cbf_ready(self, filename: str):
        imgdir = self.instrument.config['path']['directories']['images']
        os.stat(self.instrument.config['path']['directories']['images'])
        try:
            os.stat(os.path.join(imgdir, filename))
        except FileNotFoundError:
            return False
        return True

    def load_cbf(self, prefix: str, fsn: int):
        cbfbasename = '{prefix}_{fsn:0{fsndigits:d}d}.cbf'.format(prefix=prefix,
                                                                  fsndigits=self.instrument.config['path']['fsndigits'],
                                                                  fsn=fsn)
        for subpath in [prefix, '']:
            cbfname = os.path.join(
                self.instrument.config['path']['directories']['images'],
                subpath, cbfbasename)
            try:
                return readcbf(cbfname)[0]
            except FileNotFoundError:
                pass
        raise FileNotFoundError(cbfbasename)

    def load_exposure(self, prefix: str, fsn: int):
        param = self.load_param(prefix, fsn)
        cbfbasename = '{prefix}_{fsn:0{fsndigits:d}d}.cbf'.format(prefix=prefix,
                                                                  fsndigits=self.instrument.config['path']['fsndigits'],
                                                                  fsn=fsn)
        try:
            cbfname = os.path.join(
                self.instrument.config['path']['directories']['images'], prefix,
                cbfbasename)
            return SASImage.new_from_file(cbfname, param)
        except FileNotFoundError:
            cbfname = os.path.join(
                self.instrument.config['path']['directories']['images'],
                cbfbasename)
            return SASImage.new_from_file(cbfname, param)

    def load_param(self, prefix: str, fsn: int):
        picklebasename = '{prefix}_{fsn:0{fsndigits:d}d}.pickle'.format(prefix=prefix,
                                                                        fsndigits=self.instrument.config['path'][
                                                                            'fsndigits'], fsn=fsn)
        for path in [
            self.instrument.config['path']['directories']['param_override'],
            self.instrument.config['path']['directories']['param']]:
            try:
                picklename = os.path.join(
                    path, picklebasename)
                with open(picklename, 'rb') as f:
                    return pickle.load(f)
            except FileNotFoundError:
                continue
        raise FileNotFoundError(picklebasename)

    def get_mask(self, maskname: str):
        if not hasattr(self, '_masks'):
            self._masks = {}
        try:
            return self._masks[maskname]
        except KeyError:
            if not os.path.isabs(maskname):
                filename = find_in_subfolders(self.instrument.config['path']['directories']['mask'],
                                              maskname)
            else:
                filename = maskname
            m = loadmat(filename)
            self._masks[maskname] = m[
                [k for k in m.keys() if not k.startswith('__')][0]].view(bool)
            return self._masks[maskname]
