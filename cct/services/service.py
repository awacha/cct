from gi.repository import GObject
import weakref


class Service(GObject.GObject):
    """Abstract base class for a service: a part of the SAXS instrument which
    takes care for a well-defined job, such as keeping track of file sequence
    numbers or running data reduction on finished exposures.
    """

    def __init__(self, instrument):
        GObject.GObject.__init__(self)
        self.instrument = weakref.proxy(instrument)

    def _load_state(self, dictionary):
        """Load the state from a dictionary"""
        return

    def _save_state(self):
        """Save the state to a dictionary"""
        return {}
