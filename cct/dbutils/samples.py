import sqlite3
errortypes = (sqlite3.IntegrityError,)
try:
    import pymysql.err
    errortypes =(sqlite3.IntegrityError, pymysql.err.IntegrityError)
except ImportError:
    pass

def makesampletable(cursor):
    cursor.execute('CREATE TABLE IF NOT EXISTS samples ('
                   'id INT PRIMARY KEY NOT NULL,'
                   'title VARCHAR(150),'
                   'transmission FLOAT,'
                   'samplex FLOAT,'
                   'sampley FLOAT,'
                   'thickness FLOAT,'
                   'CONSTRAINT UC_Sample UNIQUE (title, transmission, samplex, sampley, thickness));')
    cursor.execute('SELECT max(id) FROM samples;')
    try:
        i = int(cursor.fetchone()[0])+1
    except TypeError:
        i=1

    cursor.execute('SELECT title, transmission, samplex, sampley, thickness FROM raw;')
    for title, transmission, samplex, sampley, thickness in cursor.fetchall():
        title = ''.join(x for x in title if x in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_- 0123456789')
        values = ['"'+title+'"']
        for v in [transmission, samplex, sampley, thickness]:
            if v is None:
                values.append('NULL')
            else:
                values.append(str(float(v)))
        try:
            cursor.execute('INSERT INTO samples(id, title, transmission, samplex, sampley, thickness) VALUES ({}, {}, {}, {}, {}, {});'.format(i, *values))
            i+=1
        except errortypes:
            pass

