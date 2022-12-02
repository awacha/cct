import pickle

import click

from .main import main


@main.command()
@click.option('--config', '-c', default='config/cct.pickle', help='Config file',
              type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True,
                              allow_dash=False, ))
@click.option('--maxlevel', '-l', default=None, help='Maximum depth', type=int)
def dumpconfig(config, maxlevel):
    """Dump the contents of a config file"""
    with open(config, 'rb') as f:
        config = pickle.load(f)
    indentation = '  '
    if not isinstance(maxlevel, int):
        maxlevel = -1
    if maxlevel < 0:
        maxlevel = None

    def dump(conf, level: int):
        if (maxlevel is not None) and (level > maxlevel):
            return
        if not isinstance(conf, dict):
            click.echo(f'{level * indentation}- {conf}')
            return
        for key in sorted(conf):
            if isinstance(conf[key], dict):
                click.echo(f'{level * indentation}{key}:')
                dump(conf[key], level + 1)
            elif isinstance(conf[key], list):
                for entry in conf[key]:
                    dump(entry, level + 1)
            else:
                click.echo(f'{indentation * level}{key}: {conf[key]}')

    dump(config, 0)
