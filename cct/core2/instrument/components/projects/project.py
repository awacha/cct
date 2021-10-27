class Project:
    projectid: str
    proposer: str
    title: str

    def __init__(self, projectid: str, proposer: str='Anonymous', title: str='Untitled'):
        self.projectid = projectid
        self.proposer = proposer
        self.title = title

    def __getstate__(self):
        return {'projectid': self.projectid, 'title': self.title, 'proposer': self.proposer}

    def __setstate__(self, state):
        self.projectid = state['projectid']
        self.title = state['title']
        self.proposer = state['proposer']

    def __str__(self) -> str:
        return f'{self.projectid}: {self.title} (by {self.proposer})'