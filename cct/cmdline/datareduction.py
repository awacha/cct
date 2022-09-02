import click
from .main import main
from ..core2.config import Config
from ..core2.instrument.components.io import IO
from ..core2.instrument.components.datareduction import DataReductionPipeLine
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@main.command()
@click.option('--firstfsn', '-f', default=None, help='First file sequence number', type=click.IntRange(0),
              prompt='First file sequence number')
@click.option('--lastfsn', '-l', default=None, help='Last file sequence number', type=click.IntRange(0),
              prompt='Last file sequence number')
@click.option('--config', '-c', default='config/cct.pickle', help='Config file',
              type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True,
                              allow_dash=False, ))
def datareduction(firstfsn: int, lastfsn: int, config):
    """Command-line data reduction routine"""
    config = Config(dicorfile=config, path='ROOT')
    config.filename = None  # inhibit autosave
    io = IO(config=config, instrument=None)
    pipeline = DataReductionPipeLine(config.asdict())
    for fsn in range(firstfsn, lastfsn + 1):
        try:
            ex = io.loadExposure(config['path']['prefixes']['crd'], fsn, raw=True, check_local=True)
        except FileNotFoundError:
            logger.warning(f'Cannot load exposure #{fsn}')
            continue
        pipeline.process(ex)


