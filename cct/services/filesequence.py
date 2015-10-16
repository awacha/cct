"""Keep track of file sequence numbers"""
import os
from gi.repository import GObject, Gio
from .service import Service

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
        self._nextfreefsn = {}
        self.reload()

    def reload(self):
        # check raw detector images
        for subdir, extension in [('images', '.cbf'), ('param', '.param'), ('param_override', '.param'),
                                  ('eval2d', '.npz'), ('eval1d', '.txt')]:
            # find all subdirectories in `directory`, including `directory`
            # itself
            directory = self.instrument.config['path']['directories'][subdir]
            for d in [directory] + find_subfolders(directory):
                # find all files
                filelist = [f for f in os.listdir(d) if f.endswith(extension)]
                # find all file prefixes, like 'crd', 'tst', 'tra', 'scn', etc.
                for c in {f.split('_')[0] for f in filelist}:
                    if c not in self._lastfsn:
                        self._lastfsn[c] = 0
                    # find the highest available FSN of the current prefix in
                    # this directory
                    maxfsn = max([int(f.split('_')[1][:len(extension)])
                                  for f in filelist if f.split('_')[0] == c])
                    if maxfsn > self._lastfsn[c]:
                        self._lastfsn[c] = maxfsn
        for c in self._lastfsn:
            if c not in self._nextfreefsn:
                self._nextfreefsn[c] = 0
            if self._nextfreefsn[c] < self._lastfsn[c]:
                self._nextfreefsn[c] = self._lastfsn[c] + 1

    def get_lastfsn(self, prefix):
        return self._lastfsn[prefix]

    def get_nextfreefsn(self, prefix, acquire=True):
        if prefix not in self._nextfreefsn:
            self._nextfreefsn[prefix] = 1
        if acquire:
            self._nextfreefsn += 1
        return self._nextfreefsn[prefix]
