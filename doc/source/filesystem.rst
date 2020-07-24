File System Layout
==================

CCT stores the files it produced as well as its settings in a single directory, from which it should always be run. The
subdirectories in the working directory of `CCT` are as follows:

- `config`:
    configuration and state files
- `eval1d` [1]_:
    evaluated 1D files (obsolete, used only in previous versions)
- `eval2d` [1]_:
    processed / reduced scattering patterns and the corresponding headers
- `images` [1]_:
    raw scattering patterns as recorded by the detector. Typically points to a network share on the detector
    computer.
- `log`:
    various log files
- `mask` [2]_:
    mask matrices
- `param` [1]_:
    metadata for scattering patterns
- `param_override` [1]_:
    when incorrect data were defined before the exposure, the corrected parameter files can be placed here. These will
    take precedence over those found in the `param` subfolder.
- `scan`:
    scan files
- `scripts`:
    automated data collection scripts
- `status`:
    the current status of the instrument is written here in a static HTML file which is updated periodically. An on-line
    status display mechanism might serve this directory over HTTP(S).
- `user`:
    user scripts, typically for correcting mistakes in metadata.

Exposures are numbered consecutively from 0. They have the form `<prefix>_<fsn>.<extn>` where `<prefix>` is used to
distinguish between various kinds of exposures (test, scan, transmission, real measurement etc.), `<fsn>` is the file
sequence number and `<extn>` is the file extension. Currently the following prefixes are known and have special meanings
(but the end user is free to use more):

- `crd`:
    real measurement
- `tst`:
    test exposures
- `scn`:
    exposures corresponding to a scan sequence
- `tra`:
    exposures for transmission measurements

The file sequence number starts from 0 and typically expressed on 5 digits, padded with leading zeros.

.. [1] These subdirectories may contain more subfolders beginning with the file name prefix, i.e. `crd`, `crd_0`,
    `crd3` etc. for the sake of better file organization.  When looking for a file, `CCT` always searches subdirectories
    with names corresponding to the file prefix, as well as the original, 1st level subdirectory.

.. [2] Mask files can be stored in an arbitrary hierarchy under this subdirectory. When looking for a mask, `CCT`
    searches recursively all directories under `mask`.