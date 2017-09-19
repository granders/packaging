#!/usr/bin/env python
#
# duo_openvpn.py
# Duo OpenVPN
# Copyright 2013 Duo Security, Inc.

__version__ = '2.1'

import base64
import email.utils
import httplib
import os
import socket
import sys
import syslog
import time
import urllib
import hashlib

def log(msg):
    msg = 'Duo OpenVPN: %s' % msg
    print(msg)

try:
    import hashlib
    import hmac
    import json
    from https_wrapper import CertValidatingHTTPSConnection
except ImportError, e:
    log('ImportError: %s' % e)
    log('Please make sure you\'re running Python 2.6 or newer')
    raise

API_RESULT_AUTH   = 'auth'
API_RESULT_ALLOW  = 'allow'
API_RESULT_DENY   = 'deny'
API_RESULT_ENROLL = 'enroll'

DEFAULT_CA_CERTS = os.path.join(os.path.dirname(__file__), 'ca_certs.pem')

CACHE_DIR = '/opt/auth_cache'
CACHE_HOURS = 12

def canon_params(params):
    """
    Return a canonical string version of the given request parameters.
    """
    # this is normalized the same as for OAuth 1.0,
    # http://tools.ietf.org/html/rfc5849#section-3.4.1.3.2
    args = []
    for (key, vals) in sorted(
        (urllib.quote(key, '~'), vals) for (key, vals) in params.items()):
        for val in sorted(urllib.quote(val, '~') for val in vals):
            args.append('%s=%s' % (key, val))
    return '&'.join(args)

def canonicalize(method, host, uri, params, date, sig_version):
    """
    Return a canonical string version of the given request attributes.
    """
    if sig_version == 1:
        canon = []
    elif sig_version == 2:
        canon = [date]
    else:
        raise NotImplementedError(sig_version)

    canon += [
        method.upper(),
        host.lower(),
        uri,
        canon_params(params),
    ]
    return '\n'.join(canon)

def sign(ikey, skey, method, host, uri, date, sig_version, params):
    """
    Return basic authorization header line with a Duo Web API signature.
    """
    canonical = canonicalize(method, host, uri, params, date, sig_version)
    if isinstance(skey, unicode):
        skey = skey.encode('utf-8')
    sig = hmac.new(skey, canonical, hashlib.sha1)
    auth = '%s:%s' % (ikey, sig.hexdigest())
    return 'Basic %s' % base64.b64encode(auth)

def normalize_params(params):
    """
    Return copy of params with strings listified
    and unicode strings utf-8 encoded.
    """
    # urllib cannot handle unicode strings properly. quote() excepts,
    # and urlencode() replaces them with '?'.
    def encode(value):
        if isinstance(value, unicode):
            return value.encode("utf-8")
        return value
    def to_list(value):
        if value is None or isinstance(value, basestring):
            return [value]
        return value
    return dict(
        (encode(key), [encode(v) for v in to_list(value)])
        for (key, value) in params.items())

class Client(object):
    sig_version = 1

    def __init__(self, ikey, skey, host,
                 ca_certs=DEFAULT_CA_CERTS,
                 sig_timezone='UTC', user_agent=None):
        """
        ca_certs - Path to CA pem file.
        """
        self.ikey = ikey
        self.skey = skey
        self.host = host
        self.port = None
        self.sig_timezone = sig_timezone
        if ca_certs is None:
            ca_certs = DEFAULT_CA_CERTS
        self.ca_certs = ca_certs
        self.user_agent = user_agent
        self.set_proxy(host=None, proxy_type=None)
        self.timeout = socket._GLOBAL_DEFAULT_TIMEOUT

    def set_proxy(self, host, port=None, headers=None,
                  proxy_type='CONNECT'):
        """
        Configure proxy for API calls. Supported proxy_type values:

        'CONNECT' - HTTP proxy with CONNECT.
        None - Disable proxy.
        """
        if proxy_type not in ('CONNECT', None):
            raise NotImplementedError('proxy_type=%s' % (proxy_type,))
        self.proxy_headers = headers
        self.proxy_host = host
        self.proxy_port = port
        self.proxy_type = proxy_type

    def api_call(self, method, path, params):
        """
        Call a Duo API method. Return a (status, reason, data) tuple.

        * method: HTTP request method. E.g. "GET", "POST", or "DELETE".
        * path: Full path of the API endpoint. E.g. "/auth/v2/ping".
        * params: dict mapping from parameter name to stringified value.
        """
        params = normalize_params(params)
        now = email.utils.formatdate()
        auth = sign(self.ikey,
                    self.skey,
                    method,
                    self.host,
                    path,
                    now,
                    self.sig_version,
                    params)
        headers = {
            'Authorization': auth,
            'Date': now,
            'Host': self.host,
        }

        if self.user_agent:
            headers['User-Agent'] = self.user_agent

        if method in ['POST', 'PUT']:
            headers['Content-type'] = 'application/x-www-form-urlencoded'
            body = urllib.urlencode(params, doseq=True)
            uri = path
        else:
            body = None
            uri = path + '?' + urllib.urlencode(params, doseq=True)

        return self._make_request(method, uri, body, headers)

    def _connect(self):
        # Host and port for the HTTP(S) connection to the API server.
        if self.ca_certs == 'HTTP':
            api_port = 80
        else:
            api_port = 443
        if self.port is not None:
            api_port = self.port

        # Host and port for outer HTTP(S) connection if proxied.
        if self.proxy_type is None:
            host = self.host
            port = api_port
        elif self.proxy_type == 'CONNECT':
            host = self.proxy_host
            port = self.proxy_port
        else:
            raise NotImplementedError('proxy_type=%s' % (self.proxy_type,))

        # Create outer HTTP(S) connection.
        if self.ca_certs == 'HTTP':
            conn = httplib.HTTPConnection(host, port)
        elif self.ca_certs == 'DISABLE':
            conn = httplib.HTTPSConnection(host, port)
        else:
            conn = CertValidatingHTTPSConnection(host,
                                                 port,
                                                 ca_certs=self.ca_certs)

        # Override default socket timeout if requested.
        conn.timeout = self.timeout

        # Configure CONNECT proxy tunnel, if any.
        if self.proxy_type == 'CONNECT':
            if hasattr(conn, 'set_tunnel'): # 2.7+
                conn.set_tunnel(self.host,
                                api_port,
                                self.proxy_headers)
            elif hasattr(conn, '_set_tunnel'): # 2.6.3+
                # pylint: disable=E1103
                conn._set_tunnel(self.host,
                                 api_port,
                                 self.proxy_headers)
                # pylint: enable=E1103

        return conn

    def _make_request(self, method, uri, body, headers):
        conn = self._connect()
        if self.proxy_type == 'CONNECT':
            # Ensure the request uses the correct protocol and Host.
            if self.ca_certs == 'HTTP':
                api_proto = 'http'
            else:
                api_proto = 'https'
            uri = ''.join((api_proto, '://', self.host, uri))
        conn.request(method, uri, body, headers)
        response = conn.getresponse()
        data = response.read()
        self._disconnect(conn)
        return (response, data)

    def _disconnect(self, conn):
        conn.close()

    def json_api_call(self, method, path, params):
        """
        Call a Duo API method which is expected to return a JSON body
        with a 200 status. Return the response data structure or raise
        RuntimeError.
        """
        (response, data) = self.api_call(method, path, params)
        return self.parse_json_response(response, data)

    def parse_json_response(self, response, data):
        """
        Return the parsed data structure or raise RuntimeError.
        """
        def raise_error(msg):
            error = RuntimeError(msg)
            error.status = response.status
            error.reason = response.reason
            error.data = data
            raise error
        if response.status != 200:
            try:
                data = json.loads(data)
                if data['stat'] == 'FAIL':
                    if 'message_detail' in data:
                        raise_error('Received %s %s (%s)' % (
                            response.status,
                            data['message'],
                            data['message_detail'],
                        ))
                    else:
                        raise_error('Received %s %s' % (
                                response.status,
                            data['message'],
                        ))
            except (ValueError, KeyError, TypeError):
                pass
            raise_error('Received %s %s' % (
                    response.status,
                    response.reason,
            ))
        try:
            data = json.loads(data)
            if data['stat'] != 'OK':
                raise_error('Received error response: %s' % data)
            return data['response']
        except (ValueError, KeyError, TypeError):
            raise_error('Received bad response: %s' % data)

def success(control):
    log('writing success code to %s' % control)

    f = open(control, 'w')
    f.write('1')
    f.close()

def failure(control):
    log('writing failure code to %s' % control)

    f = open(control, 'w')
    f.write('0')
    f.close()

def preauth(client, control, username):
    log('pre-authentication for %s' % username)

    response = client.json_api_call('POST', '/rest/v1/preauth', {
            'user': username,
    })

    log('Got response')

    result = response.get('result')
    if result == API_RESULT_AUTH:
        return response['factors'].get('default')

    status = response.get('status')
    if not status:
        log('invalid API response: %s' % response)
        failure(control)

    if result == API_RESULT_ENROLL:
        log('user %s is not enrolled: %s' % (username, status))
        failure(control)
    elif result == API_RESULT_DENY:
        log('preauth failure for %s: %s' % (username, status))
        failure(control)
    elif result == API_RESULT_ALLOW:
        log('preauth success for %s: %s' % (username, status))
        success(control)
    else:
        log('unknown preauth result: %s' % result)
        failure(control)

def auth(client, control, username, password, ipaddr):
    log('authentication for %s' % username)

    response = client.json_api_call('POST', '/rest/v1/auth', {
        'user': username,
        'factor': 'auto',
        'auto': password,
        'ipaddr': ipaddr,
    })

    result = response.get('result')
    status = response.get('status')

    if not result or not status:
        log('invalid API response: %s' % response)
        failure(control)

    if result == API_RESULT_ALLOW:
        log('auth success for %s: %s' % (username, status))
        cache_auth(username, password, ipaddr)
        success(control)
    elif result == API_RESULT_DENY:
        log('auth failure for %s: %s' % (username, status))
        failure(control)
    else:
        log('unknown auth result: %s' % result)
        failure(control)

def clean_cache():
    now = time.time()
    for f in os.listdir(CACHE_DIR):
        file = os.path.join(CACHE_DIR, f)
        if os.stat(file).st_mtime < now - 12 * 60 * 60:
            os.remove(file)

def get_hash_for_connection(username, password, ipaddr):
    connection_descriptor = json.dumps({
       username: username,
       password: password,
       ipaddr: ipaddr
    })
    sha = hashlib.sha512()
    sha.update(connection_descriptor)

    return sha.hexdigest()

def check_cache(control, username, password, ipaddr):
    clean_cache()
    connection_hash = get_hash_for_connection(username, password, ipaddr)

    if os.path.isfile(os.path.join(CACHE_DIR, connection_hash)):
        log('Using cached authentication for %s' % username)
        success(control)

def cache_auth(username, password, ipaddr):
    connection_hash = get_hash_for_connection(username, password, ipaddr)
    open(os.path.join(CACHE_DIR, connection_hash), 'w').close()

def main(Client=Client, environ=os.environ):
    control = environ.get('control')
    username = environ.get('username')
    password = environ.get('password')
    ipaddr = environ.get('ipaddr', '0.0.0.0')

    if not control or not username:
        log('required environment variables not found')
        failure(control)
        return

    def get_config(k):
        v = environ.get(k)
        if v:
            return v
        else:
            log('required configuration parameter "{0:s}" not found'.format(k))
            failure(control)

    client = Client(
        ikey=get_config('ikey'),
        skey=get_config('skey'),
        host=get_config('host'),
        user_agent='duo_openvpn/' + __version__,
    )
    if environ.get('proxy_host'):
        client.set_proxy(
            host=get_config('proxy_host'),
            port=get_config('proxy_port'),
        )

    try:
        default_factor = preauth(client, control, username)
    except Exception, e:
        log(str(e))
        failure(control)

    if not (password or default_factor):
        log('no password provided and no out-of-band factors '
            'available for username {0:s}'.format(username))
        failure(control)
    elif not password:
        password = default_factor

    try:
        check_cache(control, username, password, ipaddr)
        auth(client, control, username, password, ipaddr)
    except Exception, e:
        log(str(e))
        failure(control)

    failure(control)

if __name__ == '__main__':
    main()