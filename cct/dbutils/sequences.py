import datetime
import sqlite3
import os
import dateutil.parser
from typing import Set

class SAXSSequence:
    start_time: datetime.datetime = None
    end_time: datetime.datetime = None
    n_exposures: int=None
    firstfsn: int = None
    lastfsn: int = None
    samples: Set[str] = None
    dists: Set[float] = None
    exptime: float = None
    delay_from_previous: float=None
    user: str = None
    projectid: str = None

def findsequences(cursor, max_deadtime_between_exposures = 60):
    def complete_sequence(seq, cursor):
        cursor.execute('SELECT DISTINCT project FROM raw WHERE fsn>={} AND fsn<={} AND project IS NOT NULL;'.format(int(seq.firstfsn),int(seq.lastfsn)))
        try:
            seq.projectid = cursor.fetchall()[0][0]
        except IndexError:
            seq.projectid = None
        cursor.execute('SELECT count(fsn) FROM raw WHERE fsn>={} AND fsn<={};'.format(int(seq.firstfsn), int(seq.lastfsn)))
        seq.n_exposures = int(cursor.fetchone()[0])
        cursor.execute('SELECT DISTINCT title FROM raw WHERE fsn>={} AND fsn<={} AND title IS NOT NULL;'.format(int(seq.firstfsn), int(seq.lastfsn)))
        seq.samples = {x[0] for x in cursor.fetchall()}
        cursor.execute('SELECT sum(exposuretime) FROM raw WHERE fsn>={} AND fsn<={};'.format(int(seq.firstfsn), int(seq.lastfsn)))
        seq.exptime = float(cursor.fetchone()[0])
        cursor.execute('SELECT DISTINCT username FROM raw WHERE fsn>={} AND fsn<={} AND username IS NOT NULL;'.format(int(seq.firstfsn), int(seq.lastfsn)))
        try:
            seq.user = cursor.fetchall()[0][0]
        except IndexError:
            seq.user = None
        cursor.execute('SELECT DISTINCT distance FROM raw WHERE fsn>={} AND fsn<={};'.format(int(seq.firstfsn), int(seq.lastfsn)))
        seq.dists = {float(x[0]) for x in cursor.fetchall()}
        return seq
    seq = None
    prev_endtime = None
    cursor.execute('SELECT fsn FROM raw ORDER BY fsn ASC;')
    fsns = [r[0] for r in cursor.fetchall()]
    for fsn in fsns:
        cursor.execute('SELECT startdate, enddate FROM raw WHERE fsn={};'.format(fsn))
        sd, ed=cursor.fetchone()
        if isinstance(sd, str):
            sd, ed = [dateutil.parser.parse(x) for x in (sd, ed)]
        if (seq is None) or ((sd - seq.end_time).total_seconds()>=max_deadtime_between_exposures):
            # this is a new sequence
            if seq is not None:
                prev_endtime = seq.end_time
                yield complete_sequence(seq, cursor)
            seq = SAXSSequence()
            if prev_endtime is None:
                seq.delay_from_previous = None
            else:
                seq.delay_from_previous = (sd - prev_endtime).total_seconds()
            seq.end_time = ed
            seq.start_time = sd
            seq.firstfsn = fsn
            seq.n_exposures = 0
            seq.dists = set()
            seq.samples = set()
            seq.exptime = 0
        seq.end_time = ed
        seq.lastfsn = fsn
        seq.n_exposures +=1
    if seq is not None:
        yield complete_sequence(seq, cursor)