import warnings
warnings.filterwarnings('ignore')
from sastool.io import credo_cct, credo_saxsctrl
from sastool.classes2 import Header
import os
import sqlite3
import pickle
import datetime
import argparse
import pkg_resources
import numpy as np
from .sequences import findsequences

try:
    import pymysql.cursors
    MYSQL_SUPPORTED=True
except ImportError:
    MYSQL_SUPPORTED=False

def read_headers(path:str, config, no_load_fsns=None):
    if no_load_fsns is None:
        no_load_fsns=[]
    no_load_fsns=list(no_load_fsns)
    for subdir, subdirs, files in os.walk(path):
        for f in sorted(files):
            if not f.startswith(config['path']['prefixes']['crd']):
                continue
            basename, extension = f.split('.',1)
            fsn = int(basename.split('_',1)[1])
            if fsn in no_load_fsns:
                continue
            if f.endswith('.param') or f.endswith('.param.gz'):
                # try to see if a pickle file is there. If it is, open it instead of the .param file
                for extn in ['.pickle', '.pickle.gz']:
                    try:
                        yield credo_cct.Header.new_from_file(os.path.join(subdir, basename+extn))
                        break
                    except FileNotFoundError:
                        continue
                else:
                    # no pickle file, load the header
                    try:
                        yield credo_saxsctrl.Header.new_from_file(os.path.join(subdir, f))
                    except:
                        print('ERROR WHILE READING HEADER {}.'.format(os.path.join(subdir,f)))
                        raise
            elif f.endswith('.pickle') or f.endswith('.pickle.gz'):
                try:
                    yield credo_cct.Header.new_from_file(os.path.join(subdir, f))
                except:
                    print('ERROR WHILE READING HEADER {}.'.format(os.path.join(subdir,f)))
                    raise
            else:
                continue
            no_load_fsns.append(fsn)
    return

def run():
    global MYSQL_SUPPORTED
    parser = argparse.ArgumentParser(description="Update the exposure database")
    parser.add_argument('-o', '--output', dest='outputfile', default=None, help='Output database name')
    parser.add_argument('-f', '--force', dest='update_if_exists', action='store_const', const=True, default=False,
                        help='Update already existing lines in the database')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_const', const=True, default=False,
                        help='Verbose operation')
    parser.add_argument('-d', '--debug', dest='debug', action='store_const', const=True, default=False,
                        help='Debug mode')
    if MYSQL_SUPPORTED:
        parser.add_argument('-s', '--server', dest='server', default=None, help='MySQL/MariaDB server host name')
        parser.add_argument('-u', '--user', dest='username', default=None, help='MySQL/MariaDB user name')
        parser.add_argument('-p', '--password',dest='password', default=None, help='MySQL/MariaDB password')
    parser.add_argument('--version', action='version', version='%(prog)s {}'.format(pkg_resources.get_distribution('cct').version))
    args=parser.parse_args()

    db_outputfile = args.outputfile
    update_if_exists = args.update_if_exists
    verbose = args.verbose
    debug = args.debug


    try:
        with open('config/cct.pickle', 'rb') as f:
            config = pickle.load(f)
    except FileNotFoundError:
        config={
            'path':{'directories':{'eval2d':'eval2d',
                                   'images':'images',
                                   'param':'param',
                                   'param_override':'param_override'},
                    'fsndigits':5,
                    'prefixes':{'crd':'crd',
                                'scn':'scn',
                                'tra':'tra',
                                'tst':'tst'}}
        }
    parameters = [('fsn',int), ('absintfactor',float), ('beamcenterx',float), ('beamcentery',float),
                  ('date',datetime.datetime), ('distance', float),
                  ('distancedecrease', float), ('energy', float), ('exposuretime', float), ('flux', float),
                  ('fsn_absintref', int), ('fsn_emptybeam', int),
                  ('maskname', str), ('pixelsizex', float), ('pixelsizey', float), ('project', str),
                  ('samplex', float), ('sampley', float), ('temperature', float), ('thickness', float),
                  ('title', str), ('transmission', float), ('username', str),
                  ('vacuum', float), ('wavelength', float), ('startdate', datetime.datetime), ('enddate', datetime.datetime)]

    try:
        if args.server is not None:
            connector = pymysql.connect
            connector_kwargs = {'host':args.server, 'user':args.username, 'password':args.password, 'db':args.outputfile,
                                'charset':'utf8mb4', 'cursorclass':pymysql.cursors.Cursor}
        else:
            raise AttributeError
    except AttributeError:
        connector = sqlite3.connect
        connector_kwargs={'database':args.outputfile}
        MYSQL_SUPPORTED=False
    conn = connector(**connector_kwargs)
    try:
        c = conn.cursor()
        if not MYSQL_SUPPORTED:
            c.execute('SELECT name FROM sqlite_master WHERE type="table";')
        else:
            c.execute('SHOW TABLES;')
        tables = [x[0] for x in c.fetchall()]
        if 'raw' not in tables:
            if verbose:
                print('Creating table "raw"')
            c.execute('CREATE TABLE raw('
                      'fsn INT PRIMARY KEY NOT NULL, '+
                      ', '.join(['{} {}'.format(name, {int:'INT', str:'TEXT', float:'REAL', datetime.datetime:'DATETIME'}[type_]) for name, type_ in parameters[1:]])+');'
                      )
        if 'processed' not in tables:
            if verbose:
                print('Creating table "processed"')
            c.execute('CREATE TABLE processed('
                      'fsn INT PRIMARY KEY NOT NULL, '+
                      ', '.join(['{} {}'.format(name, {int:'INT', str:'TEXT', float:'REAL', datetime.datetime:'DATETIME'}[type_]) for name, type_ in parameters[1:]])+');'
                      )

        for tablename, rootpath in [('raw', config['path']['directories']['param']),
                                    ('processed', config['path']['directories']['eval2d'])]:
            if not MYSQL_SUPPORTED:
                insertion_query='INSERT INTO {} VALUES ({});'.format(tablename, ', '.join('?'*len(parameters)))
            else:
                insertion_query='INSERT INTO `{}` ({}) VALUES ({});'.format(
                    tablename,
                    ', '.join(["`"+p[0]+"`" for p in parameters]),
                    ', '.join(['%s']*len(parameters)))
            if verbose:
                print('Filling table "{}"'.format(tablename))
            c.execute('SELECT fsn FROM {};'.format(tablename))
            fsns = [x[0] for x in c.fetchall()]
            if update_if_exists:
                no_load_fsns=[]
            else:
                no_load_fsns=fsns
            for h in read_headers(rootpath, config, no_load_fsns):
                if verbose:
                    print('{},'.format(h.fsn), end=' ', flush=True)
                def safe_getattr(h:Header, attr:str, type_):
                    try:
                        val = getattr(h, attr)
                    except KeyError:
                        return None
                    except (TypeError, ValueError) as exc:
                        if type_ is float:
                            return np.nan
                        return None
                    if isinstance(val, type_):
                        return val
                    try:
                        return type_(val)
                    except (TypeError, ValueError) as exc:
                        if type_ is float:
                            return np.nan
                        return None
                def set_none_null(value):
                    if value is None:
                        return 'NULL'
                    elif isinstance(value, str):
                        return '"'+value+'"'
                    elif isinstance(value, datetime.datetime):
                        return '"'+str(value)+'"'
                    elif np.isnan(value):
                        return 'NULL'
                    else:
                        return str(value)
                paramvalues = [safe_getattr(h, name, type_) for name, type_ in parameters]

                if update_if_exists and paramvalues[0] in fsns:
                    c.execute('DELETE FROM {} WHERE fsn={};'.format(tablename,int(paramvalues[0])))
                if MYSQL_SUPPORTED:
                    paramvalues = [set_none_null(p) for p in paramvalues]
                    c.execute(insertion_query % tuple(paramvalues))
                else:
                    c.execute(insertion_query, tuple(paramvalues))
            conn.commit()
        # find the sequences
        c.execute('DROP TABLE IF EXISTS sequences;')
        c.execute('CREATE TABLE IF NOT EXISTS sequences ('
                  'id INT PRIMARY KEY NOT NULL,'
                  'starttime DATETIME,'
                  'endtime DATETIME,'
                  'exposurecount INT,'
                  'firstfsn INT,'
                  'lastfsn INT,'
                  'exptime FLOAT,'
                  'user TEXT,'
                  'project TEXT);')
        for i, seq in enumerate(findsequences(c)):
            c.execute('DELETE FROM sequences WHERE id ={:d};'.format(i))
            if seq.user is None:
                seq.user = 'NULL'
            else:
                seq.user= '"'+seq.user+'"'
            if seq.projectid is None:
                seq.projectid = 'NULL'
            else:
                seq.projectid = '"'+seq.projectid+'"'
            query = 'INSERT INTO sequences (`id`, `starttime`, `endtime`, `exposurecount`, `firstfsn`, `lastfsn`, `exptime`, `user`, `project`) VALUES ({0:d}, "{1.start_time}", "{1.end_time}", {1.n_exposures:d}, {1.firstfsn:d}, {1.lastfsn:d}, {1.exptime:f}, {1.user}, {1.projectid});'.format(i, seq)
            c.execute(query)
        #makesampletable(c)
    finally:
        conn.commit()
        conn.close()


