"""Keep track of file sequence numbers"""
import os
from .service import Service
import logging
import datetime
import time
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


def find_subfolders(rootdir, recursive=True):
    """Find subdirectories with a cheat: it is assumed that directory names do not
    contain periods."""
    possibledirs = [os.path.join(rootdir, x)
                    for x in os.listdir(rootdir) if '.' not in x]
    dirs = [x for x in possibledirs if os.path.isdir(x)]
    results = dirs[:]
    if recursive:
        results = dirs[:]
        for d in dirs:
            results.extend(find_subfolders(d, recursive))
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
        self._scanfile = self.instrument.config['path']['scanfile']
        if self._scanfile.split(os.sep)[0] != self.instrument.config['path']['directories']['scan']:
            self._scanfile = os.path.join(
                self.instrument.config['path']['directories']['scan'], self._scanfile)
        if not os.path.exists(self._scanfile):
            with open(self._scanfile, 'wt', encoding='utf-8') as f:
                f.write('#F %s' % os.path.abspath(self._scanfile) + '\n')
                f.write('#E %d\n' % time.time())
                f.write('#D %s\n' % time.asctime())
                f.write('#C CREDO scan file\n')
                f.write('#O0 ' + '  '.join(m['name'] for m in sorted(
                    self.instrument.config['motors'], key=lambda x: x['name'])) + '\n')
                f.write('\n')

    def reload(self):
        # check raw detector images
        for subdir, extension in [('images', '.cbf'), ('param', '.param'), ('param_override', '.param'),
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
            self._nextfreescan += 1

    def get_nextfreefsn(self, prefix, acquire=True):
        if prefix not in self._nextfreefsn:
            self._nextfreefsn[prefix] = 1
        try:
            return self._nextfreefsn[prefix]
        finally:
            if acquire:
                self._nextfreefsn[prefix] += 1

    def new_exposure(self, fsn, filename, prefix):
        """Called by various parts of the instrument if a new exposure file 
        has became available"""
        if (prefix not in self._lastfsn) or (fsn > self._lastfsn[prefix]):
            self._lastfsn[prefix] = fsn
        logger.info('New exposure: %s (fsn: %d, prefix: %s)' %
                    (filename, fsn, prefix))
        # write header file if needed
        config = self.instrument.config
        if prefix in [config['path']['prefixes']['crd'],
                      config['path']['prefixes']['tst']]:
            with open(os.path.join(self.instrument.config['path']['directories']['param'],
                                   prefix + '_' + ('%%0%dd.param' % config['path']['fsndigits']) % fsn), 'wt') as f:
                f.write('FSN:\t%d\n' % fsn)
                sample = self.instrument.samplestore.get_active()
                f.write('Sample name:\t%s\n' % sample.title)
                f.write('Sample-to-detector distance (mm):\t%18f\n' %
                        config['geometry']['dist_sample_det'])
                f.write('Sample thickness (cm):\t%18f\n' % sample.thickness)
                f.write('Sample position (cm):\t%18f\n' % sample.positiony)
                f.write('Measurement time (sec): %f\n' %
                        self.instrument.detector.get_variable('exptime'))
                f.write('Beam x y for integration:\t%18f %18f\n' % (
                    config['geometry']['beamposx'] + 1, config['geometry']['beamposy'] + 1))
                f.write('Pixel size of 2D detector (mm):\t%f\n' %
                        config['geometry']['pixelsize'])
                f.write('Primery intensity at monitor (counts/sec):\t%f\n' %
                        self.instrument.detector.get_variable('exptime'))
                f.write('Date:\t%s\n' % str(datetime.datetime.now()))
                for m in sorted(self.instrument.motors):
                    f.write('Motor[%s]:\t%f\n' %
                            self.instrument.motors[m].where())
                for d in sorted(self.instrument.devices):
                    for v in sorted(self.instrument.devices[d].list_variables()):
                        f.write(
                            '%s.%s:\t%s\n' % (d, v, self.instrument.devices[d].get_variable(v)))
                raise NotImplementedError
                # TODO: geometry, other parameters in instrument.config; Make
                # compatible with original param format (?) for XLS/sqlite
                # listing.
