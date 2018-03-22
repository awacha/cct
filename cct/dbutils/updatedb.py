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
                    yield credo_saxsctrl.Header.new_from_file(os.path.join(subdir, f))
            elif f.endswith('.pickle') or f.endswith('.pickle.gz'):
                yield credo_cct.Header.new_from_file(os.path.join(subdir, f))
            else:
                continue
            no_load_fsns.append(fsn)
    return

def run():
    parser = argparse.ArgumentParser(description="Update the exposure database")
    parser.add_argument('-o', '--output', dest='outputfile', default='exposurelist.db', help='Output file (a sqlite3 database)')
    parser.add_argument('-u', '--update-existing', dest='update_if_exists', action='store_const', const=True, default=False,
                        help='Update already existing lines in the database')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_const', const=True, default=False,
                        help='Verbose operation')
    parser.add_argument('--version', action='version', version='%(prog)s {}'.format(pkg_resources.get_distribution('cct').version))
    args=parser.parse_args()

    db_outputfile = args.outputfile
    update_if_exists = args.update_if_exists
    verbose = args.verbose

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


    with sqlite3.connect(db_outputfile) as db:
        c=db.cursor()
        tables=[x[0] for x in c.execute('SELECT name FROM sqlite_master WHERE type="table";').fetchall()]
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
            if verbose:
                print('Filling table "{}"'.format(tablename))
            fsns = [x[0] for x in c.execute('SELECT fsn FROM {};'.format(tablename)).fetchall()]
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
                    except (KeyError, TypeError):
                        return None
                    if isinstance(val, type_):
                        return val
                    try:
                        return type_(val)
                    except TypeError:
                        return None
                paramvalues = [safe_getattr(h, name, type_) for name, type_ in parameters]
                if update_if_exists and paramvalues[0] in fsns:
                    c.execute('DELETE FROM {} WHERE fsn=?;'.format(tablename), (paramvalues[0],))
                c.execute('INSERT INTO {} VALUES ({});'.format(tablename, ', '.join('?'*len(parameters))), tuple(paramvalues))
            db.commit()


