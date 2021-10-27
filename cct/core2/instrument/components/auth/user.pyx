# cython language_level=3
import hashlib
import logging
import os

from .privilege import Privilege

logger = logging.getLogger(__name__)

cdef extern from "<krb5/krb5.h>":
    ctypedef struct krb5_context:
        pass
    ctypedef struct krb5_get_init_creds_opt:
        pass
    ctypedef struct krb5_creds:
        pass
    ctypedef int krb5_error_code
    ctypedef struct krb5_principal:
        pass
    ctypedef void *krb5_prompter_fct
    ctypedef signed long krb5_deltat
    krb5_error_code krb5_init_context(krb5_context *context)
    int krb5_parse_name(krb5_context context, const char *name, krb5_principal *principal_out)
    int krb5_unparse_name(krb5_context context, krb5_principal principal_in, char ** name_out)
    int krb5_get_init_creds_opt_alloc(krb5_context context, krb5_get_init_creds_opt ** opt)
    int krb5_get_init_creds_password(krb5_context context, krb5_creds *creds, krb5_principal client,
                                     const char *password, krb5_prompter_fct prompter, void *data,
                                     krb5_deltat start_time, const char *in_tkt_service,
                                     krb5_get_init_creds_opt *k5_gic_options)

def krb5_check_pass(str username, str passwd) -> bool:
    """Check the password of a Kerberos principal

    :param username: Kerberos principal, including the realm, e.g. principal@REALM
    :type username: string
    :param passwd: password of the principal
    :type passwd: string
    :return: true if password check succeeded, otherwise False
    :rtype: bool
    :raises RuntimeError: in case of system errors
    """
    cdef krb5_context kcontext;
    cdef krb5_error_code code;
    cdef krb5_principal client;
    cdef krb5_principal server;
    cdef krb5_creds creds;
    cdef krb5_get_init_creds_opt *gic_options;

    cdef char *name = NULL
    cdef int ret

    code = krb5_init_context(&kcontext)
    if code:
        raise RuntimeError('Cannot initialize Kerberos5 context')
    ret = krb5_parse_name(kcontext, username.encode('utf-8'), &client)
    if ret:
        raise RuntimeError('Cannot parse user name.')

    krb5_get_init_creds_opt_alloc(kcontext, &gic_options)
    ret = krb5_get_init_creds_password(kcontext, &creds, client, passwd.encode('utf-8'), NULL, NULL, 0, NULL,
                                       gic_options)
    return ret == 0

cdef class User:
    cdef public str username, ldapdn, kerberosprincipal, firstname, lastname, email
    cdef str __passwordhash
    cdef set __privileges

    def __init__(self, username: str):
        self.username = username
        self.ldapdn = None
        self.kerberosprincipal = None
        self.__passwordhash = None
        self.firstname = 'Anonymous'
        self.lastname = 'Coward'
        self.email = 'invalid@example.com'
        self.__privileges = set()

    def hasPrivilege(self, privilege: Privilege) -> bool:
        return (privilege in self.__privileges) or (Privilege.SuperUser in self.__privileges)

    def grantPrivilege(self, privilege: Privilege):
        self.__privileges.add(privilege)

    def revokePrivilege(self, privilege: Privilege):
        if privilege in self.__privileges:
            self.__privileges.remove(privilege)

    def authenticatePWHash(self, password: str) -> bool:
        if not self.__passwordhash:
            logger.debug(f'No password hash for user {self.username}.')
            return False
        elif self.__passwordhash == hashlib.sha512(password.encode('utf-8')).hexdigest():
            logger.info(f'Authenticated user {self.username} using hash-based authentication.')
            return True
        else:
            logger.info(f'Authentication error for user {self.username}: password mismatch.')
            return False

    def authenticateLDAP(self, password: str) -> bool:
        try:
            import ldap3
            import ldap3.core.exceptions
        except ImportError:
            logger.debug('LDAP3 package not installed, LDAP authentication disabled.')
            return False
        uris = []
        for ldapfile in ['/etc/openldap/ldap.conf', '/etc/ldap/ldap.conf', '/usr/local/openldap/ldap.conf',
                         os.path.expanduser('~/.ldaprc'), 'ldaprc']:
            try:
                with open(ldapfile, 'rt') as f:
                    for line in f:
                        l = line.strip()
                        if not l:
                            continue
                        if l.split()[0].upper() == 'URI':
                            uris = l.split()[1:]
            except FileNotFoundError:
                continue
        logger.debug(f'LDAP URIs found: {uris}')
        for uri in uris:
            logger.debug(f'Trying URI {uri}')
            if uri.startswith('ldaps://'):
                ldaps = True
            elif uri.startswith('ldap://'):
                ldaps = False
            else:
                raise ValueError('Invalid LDAP URI: {}'.format(uri))
            server = ldap3.Server(uri[8:] if ldaps else uri[7:], port=636 if ldaps else 389, use_ssl=ldaps,
                                  get_info=ldap3.ALL)
            try:
                logger.debug(f'Trying to bind with DN {self.ldapdn}')
                with ldap3.Connection(server, user=self.ldapdn,
                                      password=password, auto_bind=ldap3.AUTO_BIND_NONE) as conn:
                    if conn.bind():
                        logger.info('Authenticated user ' + self.username + ' using LDAP.')
                        return True
                    else:
                        logger.info('Bind unsuccessful')
                        continue
            except ldap3.core.exceptions.LDAPExceptionError as exc:
                logger.debug(f'Exception while authenticating user with LDAP: {exc}')
                continue
        logger.info('Failed to authenticate user ' + self.username + ' using LDAP.')
        return False

    def authenticateKerberos(self, password: str) -> bool:
        try:
            if krb5_check_pass(self.kerberosprincipal, password):
                logger.info(f'Authenticated user {self.username} using Kerberos.')
                return True
            else:
                logger.info(f'Failed to authenticate user {self.username} using Kerberos.')
                return False
        except (RuntimeError, TypeError) as rte:
            logger.error('Kerberos error: {}'.format(str(rte)))
            return False

    def authenticate(self, password: str) -> bool:
        return self.authenticateLDAP(password) or \
               self.authenticateKerberos(password) or \
               self.authenticatePWHash(password) or \
               self.username == 'root'


    def setPassword(self, password: str):
        self.__passwordhash = hashlib.sha512(password.encode('utf-8')).hexdigest()

    def setPasswordHash(self, passwordhash: str):
        self.__passwordhash = passwordhash

    def setLDAPdn(self, ldapdn: str):
        self.ldapdn = ldapdn

    def setKerberosPrincipal(self, principal: str):
        self.kerberosprincipal = principal

    def __getstate__(self):
        return {'username': self.username,
                'passwordhash': self.__passwordhash,
                'ldapdn': self.ldapdn,
                'kerberosprincipal': self.kerberosprincipal,
                'firstname': self.firstname,
                'lastname': self.lastname,
                'email': self.email,
                'privileges': '|'.join([p.value for p in self.__privileges])
                }

    def __setstate__(self, state):
        self.username = state['username']
        self.__passwordhash = state['passwordhash']
        self.ldapdn = state['ldapdn']
        self.kerberosprincipal = state['kerberosprincipal']
        self.firstname = state['firstname']
        self.lastname = state['lastname']
        self.email = state['email']
        self.__privileges = {p for p in Privilege if p.value in state['privileges'].split('|')}

    @property
    def privileges(self):
        return list(self.__privileges)