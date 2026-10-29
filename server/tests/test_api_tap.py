import http.client
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from cloudy_labs.tap import api_tap
from cloudy_labs.tap.api_tap import ApiTap, EventHub, describe, is_write

AUTH = "AWS4-HMAC-SHA256 Credential=test/20261029/us-east-1/{service}/aws4_request, SignedHeaders=host, Signature=abc"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Upstream:
    """Records every request it gets; answers with the status the path asks for (/status/<n>).

    HEAD answers describe a 12345-byte object, as S3 HeadObject does, without sending it.
    """

    def __init__(self):
        self.requests: list[dict] = []
        received = self.requests

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def handle_one(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                received.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})
                status = int(self.path.split("/status/")[1]) if "/status/" in self.path else 200
                data = b"ok" if self.path != "/_floci/health" else b"{}"
                self.send_response(status)
                self.send_header("Content-Length", "12345" if self.command == "HEAD" else str(len(data)))
                self.send_header("X-Upstream", "yes")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = handle_one

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def tap():
    upstream = Upstream()
    t = ApiTap(upstream.url, free_port(), free_port()).start()
    t.upstream = upstream
    yield t
    t.close()
    upstream.close()


def request(tap, method, path, body=b"", headers=None, chunked=False):
    conn = http.client.HTTPConnection("127.0.0.1", tap.proxy.server_address[1], timeout=5)
    if chunked:
        conn.putrequest(method, path, skip_host=True)
        for k, v in (headers or {}).items():
            conn.putheader(k, v)
        conn.putheader("Transfer-Encoding", "chunked")
        conn.endheaders()
        for i in range(0, len(body), 5):
            piece = body[i : i + 5]
            conn.send(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
        conn.send(b"0\r\n\r\n")
    else:
        conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp, data


class SseClient:
    def __init__(self, tap):
        self.sock = socket.create_connection(("127.0.0.1", tap.events.server_address[1]), timeout=5)
        self.sock.sendall(b"GET /events HTTP/1.1\r\nHost: 127.0.0.1:4568\r\n\r\n")
        self.file = self.sock.makefile("rb")
        while self.file.readline() not in (b"\r\n", b""):  # status line and headers
            pass
        assert self.file.readline() == b": connected\n"
        self.file.readline()

    def next_event(self, timeout=2.0) -> dict:
        self.sock.settimeout(timeout)
        while True:
            line = self.file.readline()
            if line.startswith(b"data: "):
                return json.loads(line[6:])

    def close(self):
        self.sock.close()


def wait_for_subscribers(tap, n):
    deadline = time.monotonic() + 2
    while len(tap.hub._subscribers) != n:
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_forwards_request_unchanged(tap):
    body = b"Action=CreateVpc&Version=2016-11-15&CidrBlock=10.0.0.0%2F16"
    headers = {
        "Host": "127.0.0.1:4566",
        "Authorization": AUTH.format(service="ec2"),
        "X-Amz-Date": "20261029T000000Z",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }
    resp, data = request(tap, "POST", "/?x=1", body, headers)
    assert (resp.status, data, resp.getheader("X-Upstream")) == (200, b"ok", "yes")
    got = tap.upstream.requests[-1]
    assert (got["method"], got["path"], got["body"]) == ("POST", "/?x=1", body)
    for k, v in headers.items():  # Host and Authorization untouched, so SigV4 still verifies
        assert got["headers"][k] == v


def test_head_keeps_the_object_size(tap):
    headers = {"Host": "127.0.0.1:4566", "Authorization": AUTH.format(service="s3")}
    resp, data = request(tap, "HEAD", "/bucket/a.txt", headers=headers)
    assert (resp.status, resp.getheader("Content-Length"), data) == (200, "12345", b"")


def test_chunked_upload_reaches_upstream_whole(tap):
    body = b"hello chunked world"
    headers = {"Host": "127.0.0.1:4566", "Authorization": AUTH.format(service="s3")}
    resp, _ = request(tap, "PUT", "/bucket/key.txt", body, headers, chunked=True)
    assert resp.status == 200
    got = tap.upstream.requests[-1]
    assert got["body"] == body and got["headers"]["Content-Length"] == str(len(body))
    assert "Transfer-Encoding" not in got["headers"]


@pytest.mark.parametrize(
    "service, method, path, body, extra, action",
    [
        ("ec2", "POST", "/", b"Action=RunInstances&Version=2016-11-15", {"Content-Type": "application/x-www-form-urlencoded"}, "RunInstances"),
        ("ec2", "GET", "/?Action=DescribeVpcs", b"", {}, "DescribeVpcs"),
        ("dynamodb", "POST", "/", b"{}", {"X-Amz-Target": "DynamoDB_20120810.PutItem"}, "PutItem"),
        ("s3", "GET", "/", b"", {}, "ListBuckets"),
        ("s3", "PUT", "/bucket", b"", {}, "CreateBucket"),
        ("s3", "PUT", "/bucket?tagging", b"<x/>", {}, "PutBucketTagging"),
        ("s3", "GET", "/bucket?list-type=2", b"", {}, "ListObjects"),
        ("s3", "PUT", "/bucket/a/b.txt", b"data", {}, "PutObject"),
        ("s3", "PUT", "/bucket/copy.txt", b"", {"x-amz-copy-source": "/bucket/a"}, "CopyObject"),
        ("s3", "DELETE", "/bucket/a.txt", b"", {}, "DeleteObject"),
        ("s3", "POST", "/bucket?delete", b"<Delete/>", {}, "DeleteObjects"),
        ("s3", "HEAD", "/bucket/a.txt", b"", {}, "HeadObject"),
    ],
)
def test_describe(service, method, path, body, extra, action):
    headers = {"Authorization": AUTH.format(service=service)} | extra
    assert describe(headers, body, method, path) == (service, action)


def test_describe_unsigned_request():
    assert describe({}, b"", "GET", "/_floci/health") == ("?", "?")


@pytest.mark.parametrize(
    "service, action, method, write",
    [
        ("ec2", "CreateVpc", "POST", True),
        ("ec2", "AuthorizeSecurityGroupIngress", "POST", True),
        ("ec2", "RunInstances", "POST", True),
        ("ec2", "DescribeInstances", "POST", False),
        ("ec2", "WaitUntil", "POST", False),
        ("s3", "PutObject", "PUT", True),
        ("s3", "DeleteObjects", "POST", True),
        ("s3", "ListObjects", "GET", False),
        ("s3", "HeadObject", "HEAD", False),
    ],
)
def test_is_write(service, action, method, write):
    assert is_write(service, action, method) is write


def test_sse_gets_successful_writes_only(tap):
    client = SseClient(tap)
    wait_for_subscribers(tap, 1)
    form = {"Authorization": AUTH.format(service="ec2"), "Content-Type": "application/x-www-form-urlencoded"}
    request(tap, "POST", "/", b"Action=DescribeVpcs", form)  # read: no event
    request(tap, "POST", "/status/400", b"Action=CreateVpc", form)  # failed write: no event
    request(tap, "POST", "/", b"Action=CreateVpc", form)
    event = client.next_event()
    assert {k: event[k] for k in ("service", "action", "status", "write")} == {
        "service": "ec2", "action": "CreateVpc", "status": 200, "write": True,
    }
    assert event["seq"] == 1 and event["ms"] >= 0 and event["ts"] > 0
    client.close()


def test_slow_client_is_dropped_without_slowing_publish():
    hub = EventHub()
    slow = hub.subscribe()  # never reads its queue
    t0 = time.perf_counter()
    for i in range(api_tap.QUEUE_SIZE + 5):
        hub.publish({"action": f"CreateVpc{i}"})
    assert time.perf_counter() - t0 < 0.5
    assert slow.dropped.is_set() and slow not in hub._subscribers


def test_dropped_sse_client_disconnects_and_requests_still_pass(tap, monkeypatch):
    client = SseClient(tap)
    wait_for_subscribers(tap, 1)
    sub = next(iter(tap.hub._subscribers))
    tap.hub.drop(sub)
    client.sock.settimeout(2)
    assert client.file.read() == b""  # the server closed the stream
    resp, _ = request(tap, "POST", "/", b"Action=CreateVpc", {"Authorization": AUTH.format(service="ec2"), "Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status == 200
    client.close()


def test_events_refuse_a_foreign_host(tap):
    # A page on a name rebound to 127.0.0.1 sends its own name as Host.
    conn = http.client.HTTPConnection("127.0.0.1", tap.events.server_address[1], timeout=5)
    conn.request("GET", "/events", headers={"Host": "attacker.example:4568"})
    assert conn.getresponse().status == 403
    conn.close()


def test_malformed_chunked_body_answers_400(tap):
    sock = socket.create_connection(("127.0.0.1", tap.proxy.server_address[1]), timeout=5)
    sock.sendall(b"PUT /bucket/k HTTP/1.1\r\nHost: 127.0.0.1:4566\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\n")
    assert sock.makefile("rb").readline().split()[1] == b"400"
    sock.close()


def test_health_reflects_upstream(tap):
    conn = http.client.HTTPConnection("127.0.0.1", tap.events.server_address[1], timeout=5)
    conn.request("GET", "/health")
    assert conn.getresponse().status == 200
    conn.close()
    tap.upstream.close()
    conn = http.client.HTTPConnection("127.0.0.1", tap.events.server_address[1], timeout=5)
    conn.request("GET", "/health")
    assert conn.getresponse().status == 503
    conn.close()


def test_unreachable_upstream_answers_502():
    t = ApiTap(f"http://127.0.0.1:{free_port()}", free_port(), free_port()).start()
    try:
        resp, _ = request(t, "POST", "/", b"Action=CreateVpc", {"Content-Type": "application/x-www-form-urlencoded"})
        assert resp.status == 502
    finally:
        t.close()
