#!/usr/bin/env python3
"""Deploy this Flask project to PythonAnywhere using its HTTP API."""
import argparse
import http.client
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIR = {
    '.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env',
    '.idea', '.vscode', '.pytest_cache', 'dist', 'build', 'hotelsimages',
    # Live content edited from the dashboard must never be overwritten.
    'data', 'uploads',
}
SKIP_FILE = {
    'cmd.ps1', 'out.txt', 'watch.ps1', 'deploy.py', '.pa_token',
    '.gitignore', '.DS_Store', '.env', 'run.ps1', 'start.bat', 'redeploy.ps1',
    'facebook-harith-firas-last-100-posts.md',
}
PYVERS = ['3.10', '3.11', '3.9', '3.13', '3.8']

TOKEN = ''
API = ''


def get_token():
    token = (os.environ.get('PA_TOKEN') or '').strip()
    if token:
        return token
    path = os.path.join(HERE, '.pa_token')
    if os.path.isfile(path):
        token = open(path, encoding='utf-8').read().strip()
        if token:
            return token
    print('Get it at: https://www.pythonanywhere.com/account/#api_token')
    try:
        token = input('Paste your PythonAnywhere API token: ').strip()
    except EOFError:
        sys.exit('! no token. In a terminal, save it to: %s' % path)
    if not token:
        sys.exit('! no token given')
    try:
        open(path, 'w', encoding='utf-8').write(token)
        print('  saved to .pa_token (do not commit this file)')
    except OSError:
        pass
    return token


def req(method, url, data=None, headers=None):
    request_headers = {'Authorization': 'Token ' + TOKEN}
    if headers:
        request_headers.update(headers)
    for attempt in range(4):
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, response.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8', 'replace')
        except (
            urllib.error.URLError,
            http.client.RemoteDisconnected,
            TimeoutError,
        ) as error:
            if attempt == 3:
                reason = getattr(error, 'reason', error)
                sys.exit('! network error after retries: %s' % reason)
            delay = 2 ** attempt
            print('    transient network error; retrying in %ss' % delay)
            time.sleep(delay)


def form(method, path, fields):
    return req(
        method,
        API + path,
        urllib.parse.urlencode(fields).encode(),
        {'Content-Type': 'application/x-www-form-urlencoded'},
    )


def upload(remote, blob, name):
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    head = (
        '--%s\r\nContent-Disposition: form-data; name="content"; '
        'filename="%s"\r\nContent-Type: %s\r\n\r\n'
        % (boundary, name, content_type)
    ).encode()
    body = head + blob + ('\r\n--%s--\r\n' % boundary).encode()
    return req(
        'POST',
        API + '/files/path' + remote,
        body,
        {'Content-Type': 'multipart/form-data; boundary=' + boundary},
    )


def push(local, remote_root, resume_after=None):
    """Upload a file or a whole directory. Return the uploaded file count."""
    count = 0
    if os.path.isfile(local):
        with open(local, 'rb') as handle:
            code, body = upload(
                remote_root + '/' + os.path.basename(local),
                handle.read(),
                os.path.basename(local),
            )
        if code not in (200, 201):
            sys.exit('! upload failed (HTTP %s): %s' % (code, body[:300]))
        return 1
    upload_items = []
    for root, dirs, files in os.walk(local):
        dirs[:] = [
            directory for directory in dirs
            if directory not in SKIP_DIR and not directory.startswith('.')
        ]
        for filename in files:
            if filename in SKIP_FILE or filename.endswith('.bak'):
                continue
            local_path = os.path.join(root, filename)
            relative = os.path.relpath(local_path, local).replace(os.sep, '/')
            upload_items.append((relative, local_path, filename))
    upload_items.sort(key=lambda item: item[0].lower())
    skipping = bool(resume_after)
    for relative, local_path, filename in upload_items:
            if skipping:
                if relative == resume_after:
                    skipping = False
                continue
            with open(local_path, 'rb') as handle:
                code, body = upload(
                    remote_root + '/' + relative, handle.read(), filename
                )
            if code not in (200, 201):
                sys.exit(
                    '! upload failed for %s (HTTP %s): %s'
                    % (relative, code, body[:300])
                )
            count += 1
            print('    %s' % relative)
    if resume_after and skipping:
        sys.exit('! resume marker not found: %s' % resume_after)
    return count


FLASK_WSGI = '''import sys
path = %(root)r
if path not in sys.path:
    sys.path.insert(0, path)
from %(module)s import %(var)s as application
'''


def main():
    global TOKEN, API
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', required=True, help='PythonAnywhere username')
    parser.add_argument('--kind', required=True, choices=['flask'])
    parser.add_argument('--src', default=HERE, help='local project folder')
    parser.add_argument('--domain', default=None)
    parser.add_argument('--app', default='app:app')
    parser.add_argument('--remote', default=None)
    parser.add_argument('--pyversion', default=None)
    parser.add_argument('--resume-after', default=None)
    args = parser.parse_args()

    TOKEN = get_token()
    API = 'https://www.pythonanywhere.com/api/v0/user/%s' % args.user
    domain = args.domain or '%s.pythonanywhere.com' % args.user
    source = os.path.abspath(args.src)
    if not os.path.exists(source):
        sys.exit('! not found: %s' % source)
    remote = args.remote or '/home/%s/%s' % (
        args.user, os.path.basename(source.rstrip(os.sep))
    )
    wsgi_path = '/var/www/%s_wsgi.py' % domain.replace('.', '_')

    print(
        'user   : %s\ndomain : %s\nkind   : flask\nlocal  : %s\nremote : %s'
        % (args.user, domain, source, remote)
    )

    print('\n==> checking token')
    code, body = req('GET', API + '/cpu/')
    if code != 200:
        sys.exit('! token rejected (HTTP %s): %s' % (code, body[:300]))
    print('  ok')

    print('\n==> uploading')
    count = push(source, remote, args.resume_after)
    print('  ok - %d file(s)' % count)

    print('\n==> web app')
    code, body = req('GET', API + '/webapps/')
    domains = []
    if code == 200:
        try:
            domains = [app['domain_name'] for app in json.loads(body)]
        except Exception:
            pass
    if domain in domains:
        print('  ok - exists, reusing')
    else:
        created = False
        for version in ([args.pyversion] if args.pyversion else PYVERS):
            code, body = form(
                'POST', '/webapps/',
                {'domain_name': domain, 'python_version': version},
            )
            if code in (200, 201):
                print('  ok - created on Python %s' % version)
                created = True
                break
            print('  python %s -> HTTP %s %s' % (version, code, body[:160]))
        if not created:
            sys.exit(
                '! could not create web app; create it once on the Web tab, '
                'then re-run'
            )

    print('\n==> WSGI file')
    module, _, variable = args.app.partition(':')
    wsgi_body = FLASK_WSGI % {
        'root': remote,
        'module': module,
        'var': variable or 'app',
    }
    code, body = upload(
        wsgi_path, wsgi_body.encode('utf-8'), os.path.basename(wsgi_path)
    )
    if code not in (200, 201):
        sys.exit('! WSGI write failed (HTTP %s): %s' % (code, body[:300]))
    print('  ok - %s' % wsgi_path)

    form('PATCH', '/webapps/%s/' % domain, {'source_directory': remote})
    code, body = form(
        'POST', '/webapps/%s/static_files/' % domain,
        {'url': '/static/', 'path': remote + '/static'},
    )
    print('  static mapping /static/ -> HTTP %s' % code)

    print('\n==> reloading')
    code, body = form('POST', '/webapps/%s/reload/' % domain, {})
    if code not in (200, 201):
        sys.exit('! reload failed (HTTP %s): %s' % (code, body[:300]))
    print('  ok')

    print('\n' + '-' * 50)
    print('  LIVE:  https://%s' % domain)
    print(
        '  LOG :  https://www.pythonanywhere.com/user/%s/files/path/var/log/%s.error.log'
        % (args.user, domain)
    )
    print('-' * 50)


if __name__ == '__main__':
    main()
