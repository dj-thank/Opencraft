"""Real loopback HTTP tests of strict authority-adapter inputs."""
from contextlib import redirect_stderr
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest

from opencraft_server.auth import TokenAuthority
from opencraft_server.database import Database
from opencraft_server.http import OpenCraftHTTPServer, ServerContext
from opencraft_server.service import CanonicalWorldService


class HTTPSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = CanonicalWorldService(Database(Path(self.temp.name) / 'world.sqlite3'), TokenAuthority(b't' * 32))
        created = self.service.create_world(name='test', owner_display_name='owner')
        self.token = created['sessionToken']
        self.server = OpenCraftHTTPServer(('127.0.0.1', 0), ServerContext(self.service, 'test-bootstrap'))
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, body=None, authenticated=True):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + self.token
        try:
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_invite_boolean_and_integer_strings_are_rejected(self):
        for body in ({'approvalRequired': 'false'}, {'maxUses': True}, {'ttlSeconds': '3600'}):
            with self.subTest(body=body):
                status, data = self.request('POST', '/v1/invites', body)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(data)["status"], 400)

    def test_missing_session_cannot_read_world(self):
        self.assertEqual(self.request('GET', '/v1/world/context', authenticated=False)[0], 401)

    def test_rejected_post_closes_connection_before_unread_body_is_reused(self):
        for path, headers, expected in (
            ('/v1/invites', {}, 401),
            ('/v1/dev/worlds', {}, 403),
            ('/v1/missing', {'Authorization': 'Bearer ' + self.token}, 404),
        ):
            with self.subTest(path=path):
                connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
                try:
                    connection.request('POST', path, body='{}', headers={
                        'Content-Type': 'application/json', **headers,
                    })
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                    self.assertTrue(response.will_close)
                    # HTTPConnection must reconnect rather than append a request
                    # after an unread rejected request body on the old socket.
                    connection.request('GET', '/healthz')
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read())['status'], 'ok')
                finally:
                    connection.close()

    def test_successful_requests_keep_connection_reusable(self):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            for _ in range(2):
                connection.request('POST', '/v1/invites', body='{}', headers={
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + self.token,
                })
                response = connection.getresponse()
                self.assertEqual(response.status, 201)
                response.read()
                self.assertFalse(response.will_close)
                if _ == 0:
                    first_socket = connection.sock
                else:
                    self.assertIs(connection.sock, first_socket)
        finally:
            connection.close()

    def test_context_is_real_and_nonfinite_json_is_rejected(self):
        self.assertEqual(self.request('GET', '/v1/world/context')[0], 200)
        self.assertEqual(self.request('POST', '/v1/invites', {'maxUses': float('nan')})[0], 400)

    def test_request_logging_does_not_echo_query_credentials(self):
        output = io.StringIO()
        with redirect_stderr(output):
            self.request('GET', '/healthz?password=synthetic-sensitive-log-value')
        self.assertNotIn('synthetic-sensitive-log-value', output.getvalue())
        self.assertNotIn('password', output.getvalue())
