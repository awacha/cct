import logging
import sys
import traceback

import click
import colorlog

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def excepthook(exctype, exc, tb):
    formatted_tb = "\n".join(traceback.format_exception(exctype, exc, tb))
    logging.root.critical(f'Uncaught exception: {repr(exc)}\nTraceback:\n{formatted_tb}')


@click.group()
@click.option('--die-on-error/--dont-die-on-error', '-d', default=False,
              help='Die on an unhandled exception (for debugging)', type=bool, is_flag=True)
def main(die_on_error: bool):
    if not die_on_error:
        sys.excepthook = excepthook
    logging.getLogger('matplotlib').setLevel(logging.INFO)
    # logging.getLogger('matplotlib.font_manager').setLevel(logging.INFO)
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s %(levelname)s:%(name)s:%(message)s'
    ))
    logging.root.addHandler(handler)
