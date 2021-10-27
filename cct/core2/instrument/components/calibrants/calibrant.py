import datetime
from typing import Dict, Any

import dateutil.parser


class Calibrant:
    name: str
    description: str
    calibrationdate: datetime.datetime
    regex: str

    def __init__(self, name: str):
        self.name = name
        self.description = ''
        self.calibrationdate = datetime.datetime.now()
        self.regex = f'^{name}$'

    def __setstate__(self, state: Dict[str, Any]):
        self.name = state['name']
        self.description = state['description']
        self.calibrationdate = dateutil.parser.parse(state['calibrationdate'])
        self.regex = state['regex']

    def __getstate__(self) -> Dict[str, Any]:
        return {'name': self.name,
                'description': self.description,
                'calibrationdate': str(self.calibrationdate),
                'regex': self.regex,
                }
