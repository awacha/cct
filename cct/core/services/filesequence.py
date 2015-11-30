"""Keep track of file sequence numbers and do other filesystem-related jobs"""
import datetime
import logging
import os
import pickle
import re
import time

import dateutil.parser
import numpy as np
from gi.repository import GObject
from scipy.io import loadmat

from .service import Service
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

FILENAME_RE = re.compile(r'(.*/)?\w+_\d+\.\w+')


class FileSequence(Service):
    """A class to keep track on file sequence numbers and folders"""
    name = 'filesequence'

    __gsignals__={'nextfsn-changed':(GObject.SignalFlags.RUN_FIRST, None, (str, int,)),
                  'nextscan-changed':(GObject.SignalFlags.RUN_FIRST, None, (int,)),
                  'lastfsn-changed':(GObject.SignalFlags.RUN_FIRST, None, (str, int,)),
                  'lastscan-changed':(GObject.SignalFlags.RUN_FIRST, None, (int,))}

    def __init__(self, *args, **kwargs):
        Service.__init__(self, *args, **kwargs)
        self._lastfsn = {}
        self._lastscan = 0
        self._nextfreefsn = {}
        self._scanfile_toc={}
        self.init_scanfile()
        self.reload()

    def init_scanfile(self):
        self._scanfile = os.path.join(
            self.instrument.config['path']['directories']['scan'],
            self.instrument.config['scan']['scanfile'])

        if not os.path.exists(self._scanfile):
            with open(self._scanfile, 'wt', encoding='utf-8') as f:
                f.write('#F %s' % os.path.abspath(self._scanfile) + '\n')
                f.write('#E %d\n' % time.time())
                f.write('#D %s\n' % time.asctime())
                f.write('#C CREDO scan file\n')
                f.write('#O0 ' + '  '.join(sorted([m['name'] for m in
                                                   self.instrument.config['motors']],
                                                  key=lambda x: x['name'])) + '\n')
                f.write('\n')

    def new_scan(self, cmdline, comment, exptime, N, motorname):
        scanidx=self.get_nextfreescan(acquire=True)
        with open(self._scanfile, 'at', encoding='utf-8') as f:
            self._scanfile_toc[self._scanfile][scanidx] = {'pos': f.tell() + 1, 'cmd': cmdline,
                                                           'date': datetime.datetime.now()}
            f.write('\n#S %d  %s\n' % (scanidx, cmdline))
            f.write('#D %s\n'%time.asctime())
            f.write('#C %s\n'%comment)
            f.write('#T %f  (Seconds)\n'%exptime)
            f.write('#G0 0\n')
            f.write('#G1 0\n')
            f.write('#Q 0 0 0')
            entry_index=8
            p_index=-1
            for m in sorted(self.instrument.motors):
                if entry_index>=8:
                    p_index+=1
                    f.write('\n#P%d'%p_index)
                    entry_index=0
                f.write(' %f'%self.instrument.motors[m].where())
                entry_index+=1
            f.write('\n#N %d\n'%N)
            f.write('#L '+'  '.join([motorname]+self.instrument.config['scan']['columns'])+'\n')
        logger.info('Written entry for scan %d into scanfile %s'%(scanidx, self._scanfile))
        return scanidx

    def load_scan(self, index, scanfile=None):
        if scanfile is None:
            scanfile=self._scanfile
        result={}
        with open(scanfile, 'rt', encoding='utf-8') as f:
            f.seek(self._scanfile_toc[scanfile][index]['pos'], 0)
            l=f.readline().strip()
            assert(l.startswith('#S'))
            assert(int(l.split()[1])==index)
            length=None
            index=None
            while l:
                if l.startswith('#S'):
                    result['index']=int(l.split()[1])
                    result['command']=l.split(None,2)[2]
                elif l.startswith('#D'):
                    result['date']=dateutil.parser.parse(l[3:])
                elif l.startswith('#C'):
                    result['comment']=l[3:]
                elif l.startswith('#T') and l.endswith('(Seconds)'):
                    result['countingtime']=float(l.split()[1])
                elif l.startswith('#P'):
                    if 'positions' not in result:
                        result['positions']=[]
                    result['positions'].append([float(x) for x in l.split()[1:]])
                elif l.startswith('#N'):
                    length=int(l[3:])
                elif l.startswith('#L'):
                    result['signals']=l[3:].split('  ')
                    assert(length is not None)
                    result['data']=np.zeros(length, dtype=list(zip(result['signals'], [np.float]*len(result['signals']))))
                    index=0
                elif l.startswith('#'):
                    pass
                else:
                    result['data'][index]=tuple(float(x) for x in l.split())
                    index+=1
                l=f.readline().strip()
            if 'data' in result:
                result['data'] = result['data'][:index]
        return result

    def get_scans(self, scanfile):
        return self._scanfile_toc[scanfile]

    def get_scanfiles(self):
        return sorted(self._scanfile_toc.keys())

    def reload(self):
        # check raw detector images
        for subdir, extension in [('images', '.cbf'), ('param', '.param'),
                                  ('param_override', '.param'),
                                  ('eval2d', '.npz'), ('eval1d', '.txt')]:
            # find all subdirectories in `directory`, including `directory`
            # itself
            directory = self.instrument.config['path']['directories'][subdir]
            filename_regex = re.compile('(.*/)?\\w+_\\d+\\' + extension + '$')
            for d in [directory] + find_subfolders(directory):
                # find all files
                filelist = [
                    f for f in os.listdir(d) if filename_regex.match(f) is not None]
                # find all file prefixes, like 'crd', 'tst', 'tra', 'scn', etc.
                for c in {f.rsplit('.')[0].split('_')[0] for f in filelist}:
                    if c not in self._lastfsn:
                        self._lastfsn[c] = 0
                        self.emit('lastfsn-changed', c, self._lastfsn[c])
                    # find the highest available FSN of the current prefix in
                    # this directory
                    maxfsn = max([int(f.split('_')[1][:-len(extension)])
                                  for f in filelist if (f.split('_')[0] == c)])
                    if maxfsn > self._lastfsn[c]:
                        self._lastfsn[c] = maxfsn
                        self.emit('lastfsn-changed', c, self._lastfsn[c])

        for p in self.instrument.config['path']['prefixes'].values():
            if p not in self._lastfsn:
                self._lastfsn[p] = 0

        for c in self._lastfsn:
            if c not in self._nextfreefsn:
                self._nextfreefsn[c] = 0
            if self._nextfreefsn[c] < self._lastfsn[c]:
                self._nextfreefsn[c] = self._lastfsn[c] + 1
                self.emit('nextfsn-changed', c, self._nextfreefsn[c])

        # reload scans
        scanpath = self.instrument.config['path']['directories']['scan']
        for subdir in [scanpath] + find_subfolders(scanpath):
            for scanfile in [f for f in os.listdir(subdir)
                             if f.endswith('.spec')]:
                scanfile = os.path.join(subdir, scanfile)
                with open(scanfile, 'rt', encoding='utf-8') as f:
                    self._scanfile_toc[scanfile]={}
                    l=f.readline()
                    idx = None
                    while l:
                        l=l.strip()
                        if l.startswith('#S'):
                            pos=f.tell()-len(l)-1
                            start, idx, cmd = l.split(None, 2)
                            idx = int(idx)
                            self._scanfile_toc[scanfile][idx] = {'pos': pos, 'cmd': cmd}
                        elif l.startswith('#D') and idx is not None:
                            self._scanfile_toc[scanfile][idx]['date'] = dateutil.parser.parse(l.split(None, 1)[1])
                        elif l.startswith('#C') and idx is not None:
                            self._scanfile_toc[scanfile][idx]['comment'] = l.split(None, 1)[1]
                        l=f.readline()
#        for sf in self._scanfile_toc:
#            logger.debug('Max. scan index in file %s: %d'%(sf, max([k for k in self._scanfile_toc[sf]]+[0])))

        lastscan=max([max([k for k in self._scanfile_toc[sf]] + [0])
                              for sf in self._scanfile_toc] + [0])
        if self._lastscan !=lastscan:
            self._lastscan=lastscan
            self.emit('lastscan-changed', self._lastscan)

 #       logger.debug('Max. scan index: %d'%self._lastscan)
        self._nextfreescan = self._lastscan + 1
        self.emit('nextscan-changed', self._nextfreescan)

    def get_lastfsn(self, prefix):
        return self._lastfsn[prefix]

    def get_lastscan(self):
        return self._lastscan

    def get_nextfreescan(self, acquire=True):
        try:
            return self._nextfreescan
        finally:
            if acquire:
                self._nextfreescan += 1
                self.emit('nextscan-changed', self._nextfreescan)

    def get_nextfreefsn(self, prefix, acquire=True):
        if prefix not in self._nextfreefsn:
            self._nextfreefsn[prefix] = 1
        try:
            return self._nextfreefsn[prefix]
        finally:
            if acquire:
                self._nextfreefsn[prefix] += 1
                self.emit('nextfsn-changed', prefix, self._nextfreefsn[prefix])

    def get_nextfreefsns(self, prefix, N, acquire=True):
        assert (N > 0)
        if prefix not in self._nextfreefsn:
            self._nextfreefsn[prefix] = 1
        try:
            return range(self._nextfreefsn[prefix],
                         self._nextfreefsn[prefix] + N)
        finally:
            if acquire:
                self._nextfreefsn[prefix] += N
            self.emit('nextfsn-changed', prefix, self._nextfreefsn[prefix])

    def new_exposure(self, fsn, filename, prefix, startdate, argstuple=None):
        """Called by various parts of the instrument if a new exposure file
        has became available"""
        if argstuple is None:
            argstuple = ()
        if (prefix not in self._lastfsn) or (fsn > self._lastfsn[prefix]):
            self._lastfsn[prefix] = fsn
            self.emit('lastfsn-changed', prefix, self._lastfsn[prefix])
        logger.debug('New exposure: %s (fsn: %d, prefix: %s)' %
                    (filename, fsn, prefix))
        filename = filename[filename.index('images') + 7:]
        # write header file if needed
        config = self.instrument.config
        if prefix in [config['path']['prefixes']['crd'],
                      config['path']['prefixes']['tst']]:

            # construct the params dictionary
            params = {}
            paramfilename = os.path.join(
                self.instrument.config['path']['directories']['param'],
                prefix + '_' + '%%0%dd.param' %
                config['path']['fsndigits']) % fsn
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
                    logger.warning('Cannot write property: %s'%ke.args[0])
                try:
                    params['environment']['temperature'] = self.instrument.environmentcontrollers[
                        'temperature'].get_variable('temperature_internal')
                except KeyError as ke:
                    logger.warning('Cannot write property: %s'%ke.args[0])
            params['accounting'] = {}
            for k in config['services']['accounting']:
                params['accounting'][k] = config['services']['accounting'][k]

            # save the params dictionary
            with open(picklefilename, 'wb') as f:
                logger.debug('Dumping pickle file %s' % picklefilename)
                pickle.dump(params, f)

            write_legacy_paramfile(paramfilename, params)
            argstuple = argstuple + (params,)
        self.instrument.exposureanalyzer.submit(
            fsn, filename, prefix, argstuple)

    def get_prefixes(self):
        """Return the known prefixes"""
        return list(self._lastfsn.keys())

    def is_cbf_ready(self, filename):
        imgdir = self.instrument.config['path']['directories']['images']
        os.stat(self.instrument.config['path']['directories']['images'])
        try:
            os.stat(os.path.join(imgdir, filename))
        except FileNotFoundError:
            return False
        return True

    def load_exposure(self, prefix, fsn):
        picklename = os.path.join(
            self.instrument.config['path']['directories']['param'],
            prefix + '_' + '%%0%dd.pickle' %
            self.instrument.config['path']['fsndigits'] % fsn)
        try:
            cbfname = os.path.join(
                self.instrument.config['path']['directories']['images'], prefix,
                prefix + '_' + '%%0%dd.cbf' %
                self.instrument.config['path']['fsndigits'] % fsn)
            return SASImage.new_from_file(cbfname, picklename)
        except FileNotFoundError:
            cbfname = os.path.join(
                self.instrument.config['path']['directories']['images'],
                prefix + '_' + '%%0%dd.cbf' %
                self.instrument.config['path']['fsndigits'] % fsn)
            return SASImage.new_from_file(cbfname, picklename)

    def load_param(self, prefix, fsn):
        picklename = os.path.join(
            self.instrument.config['path']['directories']['param'],
            prefix + '_' + '%%0%dd.pickle' %
            self.instrument.config['path']['fsndigits'] % fsn)
        with open(picklename, 'rb') as f:
            return pickle.load(f)

    def get_mask(self, maskname):
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
