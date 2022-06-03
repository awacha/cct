import logging
import os
import shutil

import click

from .main import main

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@main.command()
@click.option('--srcdir', '-s', default=None, help='Source directory',
              type=click.Path(file_okay=False, dir_okay=True, writable=False, allow_dash=False, readable=True,
                              resolve_path=True), required=True)
@click.option('--destdir', '-d', default=None, help='Destination directory',
              type=click.Path(file_okay=False, dir_okay=True, writable=True, allow_dash=False, readable=False,
                              resolve_path=True), required=True)
@click.option('--prefix', '-p', default='crd', help='File name prefix', type=click.STRING)
@click.option('--fsndigits', default=5, type=click.IntRange(1, max_open=True))
@click.option('--firstfsn', '-f', type=click.IntRange(0, max_open=True))
@click.option('--lastfsn', '-l', type=click.IntRange(0, max_open=True))
def copyexposurerange(srcdir: str, destdir: str, prefix: str, fsndigits: int, firstfsn: int, lastfsn: int):
    """Copy an exposure range to a different directory."""
    srcdir = os.path.abspath(srcdir)
    for folder, dirnames, filenames in os.walk(srcdir):
        logger.info(f'Looking in folder {folder}')
        rp = os.path.relpath(folder, srcdir)
        for fsn in range(firstfsn, lastfsn + 1):
            for fn in [fn for fn in filenames if os.path.splitext(fn)[0] == f'{prefix}{fsn:0{fsndigits}d}']:
                os.makedirs(os.path.join(destdir, rp), exist_ok=True)
                if not os.path.exists(os.path.join(destdir, fn)):
                    logger.debug(f'Copying file {fn}')
                    shutil.copy2(os.path.join(folder, fn), os.path.join(destdir, fn))
