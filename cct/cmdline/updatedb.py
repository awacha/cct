from .main import main
import click
from .. import dbutils2

@main.command()
@click.option('--dbtype', '-t', default=None, help='Database type',
              type=click.Choice(['sqlite', 'mysql', 'mariadb'], case_sensitive=False), required=True)
@click.option('--database', '-d', default='', help='Database name (file name for sqlite)', type=str, required=True)
@click.option('--host', '-h', default='localhost', help='Database host name', type=str)
@click.option('--username', '-u', default='user', help='Database user name', type=str)
@click.option('--password', '-p', default='', help='Database password', type=str)
@click.option('--config', '-c', default='config/cct.pickle', help='Config file',
              type=click.Path(exists=True, file_okay=True, dir_okay=False, writable=False, readable=True,
                              allow_dash=False, ))
@click.option('--verbose', '-v', is_flag=True, default=False, help='Verbose operation', type=bool)
@click.option('--readall', '-a', is_flag=True, default=False,
              help='Read all headers instead of only those after the last one', type=bool)
def updatedb(dbtype: str, database: str, host: str, username: str, password: str, config: str, verbose: bool,
             readall: bool):
    """Create or update the exposure list database"""
    dbutils2.updatedb.updatedb(dbtype, host, database, username, password, config, verbose, not readall)
