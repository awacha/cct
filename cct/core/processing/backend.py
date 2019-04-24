"""Processing backend

A queue manager which handles processing (i.e. data summarization and averaging) tasks in the background,
in a separate subprocess

Given a list of file sequence numbers, processing means the following:
    - load the corrected (evaluated) scattering patterns and the corresponding metadata
    - calculate scattering curves
    - calculate an averaged scattering pattern
    -

"""

class QueueManager:
    def __init__(self,):
        pass

    def