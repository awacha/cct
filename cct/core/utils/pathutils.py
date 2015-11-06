import os


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
