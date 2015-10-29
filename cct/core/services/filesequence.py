"""Keep track of file sequence numbers and do other filesystem-related jobs"""
import os
from .service import Service
import logging
import datetime
import time
from sastool.misc.errorvalue import ErrorValue
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


def find_in_subfolders(rootdir, target, recursive=True):
    for d in [rootdir] + find_subfolders(rootdir):
        if os.path.exists(os.path.join(d, target)):
            return os.path.join(d, target)
    raise FileNotFoundError(target)


def find_subfolders(rootdir, recursive=True):
    """Find subdirectories with a cheat: it is assumed that directory names do not
    contain periods."""
    possibledirs = [os.path.join(rootdir, x)
                    for x in sorted(os.listdir(rootdir)) if '.' not in x]
    dirs = [x for x in possibledirs if os.path.isdir(x)]
    results = dirs[:]
    if recursive:
        results = dirs[:]
        for d in dirs:
            index = results.index(d)
            for subdir in reversed(find_subfolders(d, recursive)):
                results.insert(index, subdir)
    return results


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

    def new_exposure(self, fsn, filename, prefix, startdate, args):
        """Called by various parts of the instrument if a new exposure file 
        has became available"""
        if (prefix not in self._lastfsn) or (fsn > self._lastfsn[prefix]):
            self._lastfsn[prefix] = fsn
        logger.info('New exposure: %s (fsn: %d, prefix: %s)' %
                    (filename, fsn, prefix))
        filename = filename[filename.index('images') + 7:]
        # write header file if needed
        config = self.instrument.config
        if prefix in [config['path']['prefixes']['crd'],
                      config['path']['prefixes']['tst']]:
            with open(os.path.join(self.instrument.config['path']['directories']['param'],
                                   prefix + '_' + ('%%0%dd.param' % config['path']['fsndigits']) % fsn), 'wt') as f:
                logger.debug(
                    'Writing param file for new exposure to %s' % f.name)
                f.write('FSN:\t%d\n' % fsn)
                dist = ErrorValue(config['geometry']['dist_sample_det'],
                                  config['geometry']['dist_sample_det.err'])
                sample = self.instrument.samplestore.get_active()
                distcalib = dist - sample.distminus
                f.write('Sample name:\t%s\n' % sample.title)
                f.write('Sample-to-detector distance (mm):\t%18f\n' %
                        distcalib.val)
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
                for m in sorted(self.instrument.motors):
                    f.write('motor.%s:\t%f\n' %
                            self.instrument.motors[m].where())
                for d in sorted(self.instrument.devices):
                    for v in sorted(self.instrument.devices[d].list_variables()):
                        f.write(
                            '%s.%s:\t%s\n' % (d, v, self.instrument.devices[d].get_variable(v)))
                f.write(sample.toparam())
                for k in config['geometry']:
                    f.write('geometry.%s:\t%s\n' % (k, config['geometry'][k]))
                for k in config['accounting']:
                    f.write('accounting.%s:\t%s\n' %
                            (k, config['accounting'][k]))

                f.write('ThicknessError:\t%18f\n' % sample.thickness.err)
                f.write('PosSampleError:\t%18f\n' % sample.positiony.err)
                f.write('PosSampleX:\t%18f\n' % sample.positionx.val)
                f.write('PosSampleXError:\t%18f\n' % sample.positionx.err)
                f.write('EndDate:\t%s\n' % str(datetime.datetime.now()))
                f.write('DistMinus:\t%18f\n' % sample.distminus.val)
                f.write('DistMinusErr:\t%18f\n' % sample.distminus.err)
                f.write('SetupDescription:\t%s\n' %
                        config['geometry']['description'])
                f.write('DistError:\t%s\n' % dist.err)
                f.write('XPixel:\t%18f\n' % config['geometry']['pixelsize'])
                f.write('YPixel:\t%18f\n' % config['geometry']['pixelsize'])
                f.write('TransmError:\t%18f\n' % sample.transmission.err)
                f.write('Owner:\t%18f\n' % config['accounting']['operator'])
                f.write('PosSampleError:\t%18f\n' % sample.positiony.err)
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
        self.instrument.exposureanalyzer.submit(
            fsn, filename, prefix, args)

    def get_prefixes(self):
        """Return the known prefixes"""
        return list(self._lastfsn.keys())