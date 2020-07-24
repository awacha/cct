import logging
import weakref

from ...config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class Component:
    """Logical component of an instrument"""
    config: Config
    instrument: "Instrument"

    def __init__(self, **kwargs):  # see https://www.riverbankcomputing.com/static/Docs/PyQt5/multiinheritance.html
#        super().__init__(**kwargs)
        logger.debug('Initializing a component')
        self.config = kwargs['config']
        self.config.changed.connect(self.onConfigChanged)
        self.instrument = weakref.proxy(kwargs['instrument'])
        logger.debug('Loading component state from the config')
        self.loadFromConfig()
        logger.debug('Initialized the component')

    def onConfigChanged(self, path, value):
        pass

    def saveToConfig(self):
        pass

    def loadFromConfig(self):
        pass
