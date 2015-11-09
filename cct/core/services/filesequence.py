"""Keep track of file sequence numbers and do other filesystem-related jobs"""
import datetime
import logging
import os
import pickle
import time
import numpy as np
import dateutil.parser

from scipy.io import loadmat

from .service import Service
from ..utils.errorvalue import ErrorValue
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


class FileSequence(Service):
    """A class to keep track on file sequence numbers and folders"""
    name = 'filesequence'

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
                f.write('#O0 ' + '  '.join(m['name'] for m in sorted(
                    self.instrument.config['motors'],
                    key=lambda x: x['name'])) + '\n')
                f.write('\n')

    def new_scan(self, cmdline, comment, exptime, N, motorname):
        scanidx=self.get_nextfreescan(acquire=True)
        with open(self._scanfile, 'at', encoding='utf-8') as f:
            self._scanfile_toc[self._scanfile][scanidx]=f.tell()
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
            f.seek(self._scanfile_toc[scanfile][index],0)
            l=f.readline().strip()
            logger.debug('Loaded line: %s'%l)
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
        return result

    def reload(self):
        # check raw detector images
        for subdir, extension in [('images', '.cbf'), ('param', '.param'),
                                  ('param_override', '.param'),
                                  ('eval2d', '.npz'), ('eval1d', '.txt')]:
            # find all subdirectories in `directory`, including `directory`
            # itself
            directory = self.instrument.config['path']['directories'][subdir]
            for d in [directory] + find_subfolders(directory):
                # find all files
                filelist = [
                    f for f in os.listdir(d) if f.endswith(extension)
                    and '_' in f]
                # find all file prefixes, like 'crd', 'tst', 'tra', 'scn', etc.
                for c in {f.rsplit('.')[0].split('_')[0] for f in filelist}:
                    if c not in self._lastfsn:
                        self._lastfsn[c] = 0
                    # find the highest available FSN of the current prefix in
                    # this directory
                    maxfsn = max([int(f.split('_')[1][:-len(extension)])
                                  for f in filelist if (f.split('_')[0] == c)])
                    if maxfsn > self._lastfsn[c]:
                        self._lastfsn[c] = maxfsn

        for p in self.instrument.config['path']['prefixes'].values():
            if p not in self._lastfsn:
                self._lastfsn[p] = 0

        for c in self._lastfsn:
            if c not in self._nextfreefsn:
                self._nextfreefsn[c] = 0
            if self._nextfreefsn[c] < self._lastfsn[c]:
                self._nextfreefsn[c] = self._lastfsn[c] + 1

        # reload scans
        scanpath = self.instrument.config['path']['directories']['scan']
        for subdir in [scanpath] + find_subfolders(scanpath):
            for scanfile in [f for f in os.listdir(subdir)
                             if f.endswith('.spec')]:
                scanfile = os.path.join(subdir, scanfile)
                logger.debug('Parsing scanfile %s'%scanfile)
                with open(scanfile, 'rt', encoding='utf-8') as f:
                    self._scanfile_toc[scanfile]={}
                    l=f.readline()
                    while l:
                        l=l.strip()
                        if l.startswith('#S'):
                            pos=f.tell()-len(l)-1
                            idx=int(l.split()[1])
                            self._scanfile_toc[scanfile][idx]=pos
                            logger.debug('Scan #%d at %d'%(idx,pos))
                        l=f.readline()
        for sf in self._scanfile_toc:
            logger.debug('Max. scan index in file %s: %d'%(sf, max([k for k in self._scanfile_toc[sf]]+[0])))

        self._lastscan = max([max([k for k in self._scanfile_toc[sf]] + [0])
                              for sf in self._scanfile_toc] + [0])
        logger.debug('Max. scan index: %d'%self._lastscan)
        self._nextfreescan = self._lastscan + 1

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

    def get_nextfreefsn(self, prefix, acquire=True):
        if prefix not in self._nextfreefsn:
            self._nextfreefsn[prefix] = 1
        try:
            return self._nextfreefsn[prefix]
        finally:
            if acquire:
                self._nextfreefsn[prefix] += 1

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

    def new_exposure(self, fsn, filename, prefix, startdate, argstuple=None):
        """Called by various parts of the instrument if a new exposure file
        has became available"""
        if argstuple is None:
            argstuple = ()
        if (prefix not in self._lastfsn) or (fsn > self._lastfsn[prefix]):
            self._lastfsn[prefix] = fsn
        logger.info('New exposure: %s (fsn: %d, prefix: %s)' %
                    (filename, fsn, prefix))
        filename = filename[filename.index('images') + 7:]
        # write header file if needed
        config = self.instrument.config
        if prefix in [config['path']['prefixes']['crd'],
                      config['path']['prefixes']['tst']]:
            params = {}
            with open(os.path.join(
                      self.instrument.config['path']['directories']['param'],
                      prefix + '_' + '%%0%dd.param' %
                      config['path']['fsndigits']) % fsn, 'wt') as f:
                params['fsn'] = fsn
                logger.debug(
                    'Writing param file for new exposure to %s' % f.name)
                f.write('FSN:\t%d\n' % fsn)
                dist = ErrorValue(config['geometry']['dist_sample_det'],
                                  config['geometry']['dist_sample_det.err'])
                sample = self.instrument.samplestore.get_active()
                if sample is not None:
                    params['sample'] = sample
                    distcalib = dist - sample.distminus
                    f.write('Sample name:\t%s\n' % sample.title)
                else:
                    distcalib = dist
                f.write('Sample-to-detector distance (mm):\t%18f\n' %
                        distcalib.val)
                if sample is not None:
                    f.write('Sample thickness (cm):\t%18f\n' % sample.thickness)
                    f.write('Sample position (cm):\t%18f\n' % sample.positiony)
                f.write('Measurement time (sec): %f\n' %
                        self.instrument.detector.get_variable('exptime'))
                f.write('Beam x y for integration:\t%18f %18f\n' % (
                    config['geometry']['beamposx'] + 1, config['geometry']['beamposy'] + 1))
                f.write('Pixel size of 2D detector (mm):\t%f\n' %
                        config['geometry']['pixelsize'])
                f.write('Primary intensity at monitor (counts/sec):\t%f\n' %
                        self.instrument.detector.get_variable('exptime'))
                f.write('Date:\t%s\n' % str(datetime.datetime.now()))
                params['motors'] = {}
                for m in sorted(self.instrument.motors):
                    f.write('motor.%s:\t%f\n' %
                            (m, self.instrument.motors[m].where()))
                    params['motors'][m] = self.instrument.motors[m].where()
                params['devices'] = {}
                for d in sorted(self.instrument.devices):
                    params['devices'][d] = {}
                    for v in sorted(self.instrument.devices[d].list_variables()):
                        f.write(
                            'devices.%s.%s:\t%s\n' % (d, v, self.instrument.devices[d].get_variable(v)))
                        params['devices'][d][v] = self.instrument.devices[d].get_variable(v)
                if sample is not None:
                    f.write(sample.toparam())
                    params['sample'] = sample.todict()
                params['geometry'] = {}
                for k in config['geometry']:
                    f.write('geometry.%s:\t%s\n' % (k, config['geometry'][k]))
                    params['geometry'][k] = config['geometry'][k]
                params['geometry']['truedistance'] = distcalib.val
                params['geometry']['truedistance.err'] = distcalib.err
                params['accounting'] = {}
                for k in config['accounting']:
                    f.write('accounting.%s:\t%s\n' %
                            (k, config['accounting'][k]))
                    params['accounting'][k] = config['accounting'][k]
                if sample is not None:
                    f.write('ThicknessError:\t%18f\n' % sample.thickness.err)
                    f.write('PosSampleError:\t%18f\n' % sample.positiony.err)
                    f.write('PosSampleX:\t%18f\n' % sample.positionx.val)
                    f.write('PosSampleXError:\t%18f\n' % sample.positionx.err)
                    f.write('DistMinus:\t%18f\n' % sample.distminus.val)
                    f.write('DistMinusErr:\t%18f\n' % sample.distminus.err)
                    f.write('TransmError:\t%18f\n' % sample.transmission.err)
                    f.write('PosSampleError:\t%18f\n' % sample.positiony.err)
                f.write('EndDate:\t%s\n' % str(datetime.datetime.now()))
                f.write('SetupDescription:\t%s\n' %
                        config['geometry']['description'])
                f.write('DistError:\t%s\n' % dist.err)
                f.write('XPixel:\t%18f\n' % config['geometry']['pixelsize'])
                f.write('YPixel:\t%18f\n' % config['geometry']['pixelsize'])
                f.write('Owner:\t%s\n' % config['accounting']['operator'])
                f.write('__Origin__:\tCCT\n')
                f.write('MonitorError:\t0\n')
                f.write('Wavelength:\t%18f\n' %
                        config['geometry']['wavelength'])
                f.write('WavelengthError:\t%18f\n' %
                        config['geometry']['wavelength.err'])
                f.write('__particle__:\tphoton\n')
                f.write('Project:\t%s\n' % config['accounting']['projectname'])
                f.write('maskid:\t%s\n' %
                        config['geometry']['mask'].rsplit('.', 1)[0])
                f.write('StartDate:\t%s\n' % str(startdate))
            with open(os.path.join(self.instrument.config['path']['directories']['param'],
                                   prefix + '_' + ('%%0%dd.pickle' % config['path']['fsndigits']) % fsn), 'wb') as f:
                pickle.dump(params, f)
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
        cbfname = os.path.join(
            self.instrument.config['path']['directories']['images'],
            prefix + '_' + '%%0%dd.cbf' %
            self.instrument.config['path']['fsndigits'] % fsn)
        picklename = os.path.join(
            self.instrument.config['path']['directories']['param'],
            prefix + '_' + '%%0%dd.pickle' %
            self.instrument.config['path']['fsndigits'] % fsn)
        return SASImage.new_from_file(cbfname, picklename)

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
