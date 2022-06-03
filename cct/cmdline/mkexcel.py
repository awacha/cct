import click

from .main import main
from .. import dbutils2


@main.command()
@click.option('--filename', '-o', default=None, help='Excel file name (*.xlsx typically)',
              type=click.Path(file_okay=True, dir_okay=False, writable=True, allow_dash=False), required=True)
@click.option('--firstfsn', '-f', default=0, help='First FSN', type=int, required=True)
@click.option('--lastfsn', '-l', default=1000, help='Last FSN', type=int, required=True)
@click.option('--config', '-c', default='config/cct.pickle', help='Config file',
              type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True,
                              allow_dash=False, ))
@click.option('--verbose', '-v', is_flag=True, default=False, help='Verbose operation', type=bool)
def mkexcel(filename: str, firstfsn: int, lastfsn: int, config: str, verbose: bool):
    """Create or update the exposure list database"""
    dbutils2.mkexcel.mkexcel(filename=filename, firstfsn=firstfsn, lastfsn=lastfsn, configfile=config,
                             verbose=verbose)
