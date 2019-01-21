"""Kerberos password checker

This module contains a simple function, :function:`krb5_check_pass` for checking if a password is valid for a principal.
"""

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
    int krb5_unparse_name(krb5_context context, krb5_principal principal_in, char **name_out)
    int krb5_get_init_creds_opt_alloc(krb5_context context, krb5_get_init_creds_opt **opt)
    int krb5_get_init_creds_password(krb5_context context, krb5_creds *creds, krb5_principal client, const char *password, krb5_prompter_fct prompter, void *data, krb5_deltat start_time, const char *in_tkt_service, krb5_get_init_creds_opt *k5_gic_options)

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
    ret = krb5_get_init_creds_password(kcontext, &creds, client, passwd.encode('utf-8'), NULL, NULL, 0, NULL, gic_options)
    return ret==0
