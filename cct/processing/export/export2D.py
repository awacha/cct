import numpy as np
import scipy.io
import h5py

def _matrices(group:h5py.Group):
    return group['image'], group['image_uncertainty'], group['mask']

def exportNumpy(basename, group:h5py.Group):
    intensity, error, mask = _matrices(group)
    np.savez(basename+'.npz', intensity=intensity, error=error, mask=mask)

def exportMatlab(basename, group:h5py.Group):
    intensity, error, mask = _matrices(group)
    scipy.io.savemat(basename+'.mat', {'intensity': intensity, 'error': error, 'mask': mask}, do_compression=True)

def exportAscii(basename, group:h5py.Group, gzip=False):
    gzipextn=['', '.gz'][gzip]
    intensity, error, mask = _matrices(group)
    np.savetxt(basename+'_intensity.txt'+gzipextn, intensity)
    np.savetxt(basename+'_error.txt'+gzipextn, error)
    np.savetxt(basename+'_mask.txt'+gzipextn, mask)

