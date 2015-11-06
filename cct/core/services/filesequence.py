"""Keep track of file sequence numbers and do other filesystem-related jobs"""
import datetime
import logging
import os
import pickle
import time

from sastool.io.twodim import readcbf
from scipy.io import loadmat

from .service import Service
from ..utils.errorvalue import ErrorValue
from ..utils.pathutils import find_in_subfolders, find_subfolders

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
        self._scanfiles = {}
        self._nextfreefsn = {}
        self.init_scanfile()
        self.reload()

    def init_scanfile(self):
        self._scanfile = os.path.join(self.instrument.config['path']['directories']['scan'],self.instrument.config['scan']['scanfile'])

        if not os.path.exists(self._scanfile):
            with open(self._scanfile, 'wt', encoding='utf-8') as f:
                f.write('#F %s' % os.path.abspath(self._scanfile) + '\n')
                f.write('#E %d\n' % time.time())
                f.write('#D %s\n' % time.asctime())
                f.write('#C CREDO scan file\n')
                f.write('#O0 ' + '  '.join(m['name'] for m in sorted(
                    self.instrument.config['motors'], key=lambda x: x['name'])) + '\n')
                f.write('\n')

    def start_scan(self):
        pass

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
                    f for f in os.listdir(d) if f.endswith(extension) and '_' in f]
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
                self._lastfsn[p]=0

        for c in self._lastfsn:
            if c not in self._nextfreefsn:
                self._nextfreefsn[c] = 0
            if self._nextfreefsn[c] < self._lastfsn[c]:
                self._nextfreefsn[c] = self._lastfsn[c] + 1


        # reload scans
        scanpath = self.instrument.config['path']['directories']['scan']
        for subdir in [scanpath] + find_subfolders(scanpath):
            for scanfile in [f for f in os.listdir(subdir) if f.endswith('.spec')]:
                scanfile = os.path.join(subdir, scanfile)
                with open(scanfile, 'rt', encoding='utf-8') as f:
                    self._scanfiles[scanfile] = [
                        int(l.split()[1]) for l in f if l.startswith('#S')]
        self._lastscan = max([max(self._scanfiles[sf] + [0])
                              for sf in self._scanfiles] + [0])
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
            return range(self._nextfreefsn[prefix], self._nextfreefsn[prefix] + N)
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
            with open(os.path.join(self.instrument.config['path']['directories']['param'],
                                   prefix + '_' + ('%%0%dd.param' % config['path']['fsndigits']) % fsn), 'wt') as f:
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
        cbfname = os.path.join(self.instrument.config['path']['directories']['images'],
                               prefix + '_' + '%%0%dd' % self.instrument.config['path']['fsndigits'] % fsn + '.cbf')
        data, header = readcbf(cbfname, load_header=True, load_data=True)
        with open(os.path.join(self.instrument.config['path']['directories']['param'],
                               prefix + '_' + ('%%0%dd.pickle' % self.instrument.config['path']['fsndigits']) % fsn),
                  'rb') as f:
            param = pickle.load(f)
        param['cbf'] = header
        mask = self.get_mask(param['geometry']['mask'])
        return data, mask, param

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
