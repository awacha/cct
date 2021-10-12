import logging
import os
from typing import Final

import sqlalchemy, sqlalchemy.exc, sqlalchemy.sql

from ..core2.config import Config
from ..core2.dataclasses import Header

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAXNOTFOUNDCOUNT: Final[int] = 100


def listsubdirs(path: str):
    yield path
    for fn in os.listdir(path):
        if os.path.isdir(fn):
            yield from listsubdirs(os.path.join(path, fn))


def updatedb(dbtype: str, host: str, database: str, username: str, password: str, configfile: str, verbose: bool, updateonly: bool=True):
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    config = Config(dicorfile=configfile)
    config.filename = None  # inhibit auto-save
    if dbtype.lower() == 'sqlite':
        engine = sqlalchemy.create_engine(f'sqlite:///{database}')
    elif (dbtype.lower() == 'mysql') or (dbtype.lower() == 'mariadb'):
        engine = sqlalchemy.create_engine(f'mysql://{username}:{password}@{host}/{database}')
    else:
        raise ValueError(f'Unknown database type: {dbtype}')
    meta = sqlalchemy.MetaData()
    table = sqlalchemy.Table(
        'exposures', meta,
        sqlalchemy.Column('fsn', sqlalchemy.Integer, primary_key=True),
        sqlalchemy.Column('title', sqlalchemy.Text),
        sqlalchemy.Column('distance', sqlalchemy.Float),
        sqlalchemy.Column('distancedecrease', sqlalchemy.Float),
        sqlalchemy.Column('exposuretime', sqlalchemy.Float),
        sqlalchemy.Column('temperature', sqlalchemy.Float),
        sqlalchemy.Column('thickness', sqlalchemy.Float),
        sqlalchemy.Column('transmission', sqlalchemy.Float),
        sqlalchemy.Column('date', sqlalchemy.DateTime),
        sqlalchemy.Column('beamcenterx', sqlalchemy.Float),
        sqlalchemy.Column('beamcentery', sqlalchemy.Float),
        sqlalchemy.Column('samplex', sqlalchemy.Float),
        sqlalchemy.Column('sampley', sqlalchemy.Float),
        sqlalchemy.Column('maskname', sqlalchemy.Text),
        sqlalchemy.Column('vacuum', sqlalchemy.Float),
        sqlalchemy.Column('username', sqlalchemy.Text),
        sqlalchemy.Column('project', sqlalchemy.Text),
        sqlalchemy.Column('fsn_emptybeam', sqlalchemy.Integer),
        sqlalchemy.Column('fsn_absintref', sqlalchemy.Integer),
        sqlalchemy.Column('fsn_dark', sqlalchemy.Integer),
        sqlalchemy.Column('absintfactor', sqlalchemy.Float),
        sqlalchemy.Column('flux', sqlalchemy.Float),
    )
    meta.create_all(engine)
    connection = engine.connect()
    notfoundcount = 0
    if updateonly:
        lastfsn = connection.execute(sqlalchemy.select([sqlalchemy.sql.func.max(table.c.fsn)])).fetchone()[0]
        fsn = 0 if lastfsn is None else lastfsn + 1
    else:
        fsn = 0
    subdirs = []
    for subpath in ['eval2d', 'param_override', 'param']:
        subdirs.extend(listsubdirs(config['path']['directories'][subpath]))
    while notfoundcount < MAXNOTFOUNDCOUNT:
        for subdir in subdirs:
            try:
                header = Header(
                    filename=os.path.join(
                        subdir,
                        f'{config["path"]["prefixes"]["crd"]}_{fsn:0{config["path"]["fsndigits"]}d}.pickle'))
                logger.debug(f'Found header {header.fsn} in {subdir}')
                params = dict(
                    fsn=header.fsn, title=header.title, distance=header.distance[0],
                    distancedecrease=header.distancedecrease[0], exposuretime=header.exposuretime[0],
                    temperature=header.temperature[0], thickness=header.thickness[0],
                    transmission=header.transmission[0], date=header.date,
                    beamcenterx=header.beamposcol[0], beamcentery=header.beamposrow[0],
                    samplex=header.samplex[0], sampley=header.sampley[0],
                    maskname=header.maskname, vacuum=header.vacuum[0],
                    username=header.username, project=header.project,
                    fsn_emptybeam=header.fsn_emptybeam, fsn_absintref=header.fsn_absintref,
                    fsn_dark=header.fsn_dark, absintfactor=header.absintfactor[0],
                    flux=header.flux[0],
                )
                ins = table.insert().values(**params)
                try:
                    connection.execute(ins)
                except sqlalchemy.exc.IntegrityError:
                    # this fsn already exists, do an UPDATE instead.
                    upd = table.update().where(table.c.fsn==header.fsn).values(**params)
                    connection.execute(upd)
                notfoundcount = 0
                fsn += 1
                break  # do not look further in other subdirectories
            except FileNotFoundError:
                # file not found in this subdirectory: look for it in another one.
                continue
        else:
            logger.debug(f'Not found {fsn}. {notfoundcount=}')
            fsn +=1
            notfoundcount += 1
            continue
