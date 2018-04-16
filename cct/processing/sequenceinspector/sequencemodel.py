from PyQt5 import QtCore
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Integer, DateTime, Float, String, Column

Base = declarative_base()
class Sequence(Base):
    __tablename__ = 'sequences'
    id = Column(Integer, primary_key=True)
    starttime = Column(DateTime)
    endtime = Column(DateTime)
    exposurecount = Column(Integer)
    firstfsn = Column(Integer)
    lastfsn = Column(Integer)
    exptime = Column(Float)
    user = Column(String)
    project = Column(String)

class SequenceModel(QtCore.QAbstractItemModel):
    def __init__(self, url:str):
        super().__init__(None)
        self._url = url
        self.connectDB()

    def connectDB(self):
        print('Connecting to engine: {}'.format(self._url))
        self._engine = create_engine(self._url)
        self._engine.connect()
        self._SessionClass = sessionmaker(bind=self._engine)
        self._session = self._SessionClass()
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._queryresults = self._session.query(Sequence).all()
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = ...):
        return len(self._queryresults)

    def columnCount(self, parent: QtCore.QModelIndex = ...):
        return 9

    def parent(self, child: QtCore.QModelIndex):
        return QtCore.QModelIndex()

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...):
        return self.createIndex(row, column, None)

    def flags(self, index: QtCore.QModelIndex):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemNeverHasChildren | QtCore.Qt.ItemIsSelectable

    def data(self, index: QtCore.QModelIndex, role: int = ...):
        seq = self._queryresults[index.row()]
        assert isinstance(seq, Sequence)
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return str(seq.id)
            elif index.column() == 1:
                return str(seq.starttime)
            elif index.column() == 2:
                return str(seq.endtime)
            elif index.column() == 3:
                return str(seq.firstfsn)
            elif index.column() == 4:
                return str(seq.lastfsn)
            elif index.column() == 5:
                return str(seq.exposurecount)
            elif index.column() == 6:
                return '{:.1f}'.format(seq.exptime/3600)
            elif index.column() == 7:
                return seq.user
            elif index.column() == 8:
                return seq.project
            else:
                return None
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...):
        if orientation == QtCore.Qt.Horizontal and role==QtCore.Qt.DisplayRole:
            return ['ID', 'Start', 'End', 'First FSN', 'Last FSN', 'Count', 'Exposure time (h)', 'User', 'Project'][section]
        return None

    def cleanup(self):
        self.beginResetModel()
        self._session.close()
        self._engine.dispose()
        self._queryresults=[]
        self._url = None
        self._SessionClass = None
        self.endResetModel()