#!/usr/bin/env python3
"""Pass-through proxy in front of Floci that announces every write call (stdlib only).

It runs as its own compose service from a bare Python image, so it must not import
anything outside the standard library. The learner's CLI talks to it on port 4566;
it forwards each request unchanged (Host and Authorization included, so SigV4 stays
valid) and, once Floci has answered without error, publishes an event on a
Server-Sent Events stream at :4568/events.

Environment: TAP_UPSTREAM (default http://floci:4566), TAP_PORT (4566),
TAP_EVENTS_PORT (4568), TAP_BIND (0.0.0.0; compose publishes the ports on
127.0.0.1 only).
"""

import http.client
import itertools
import json
import os
import queue
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HOP_BY_HOP = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer"}
SCOPE = re.compile(r"Credential=[^/]+/\d+/[^/]+/([^/]+)/aws4_request")
WRITE_PREFIXES = (
    "Create Delete Modify Put Attach Detach Associate Disassociate Allocate Release Run Terminate "
    "Start Stop Reboot Authorize Revoke Replace Update Import Enable Disable Assign Unassign Tag Untag"
).split()
READ_METHODS = {"GET", "HEAD"}
# S3 bucket subresources that name their own action, e.g. PUT /bucket?tagging -> PutBucketTagging.
S3_SUBRESOURCES = {
    "acl": "Acl", "cors": "Cors", "encryption": "Encryption", "lifecycle": "Lifecycle",
    "policy": "Policy", "tagging": "Tagging", "versioning": "Versioning", "website": "Website",
}
S3_VERBS = {"GET": "Get", "PUT": "Put", "DELETE": "Delete", "HEAD": "Head", "POST": "Post"}
QUEUE_SIZE = 256  # events buffered per SSE client before it counts as too slow and is dropped
KEEPALIVE_S = 15
HEALTH_PATH = "/_floci/health"


def describe(headers, body: bytes, method: str, path: str) -> tuple[str, str]:
    """(service, action) of an AWS request, from the SigV4 scope and the protocol in use."""
    m = SCOPE.search(headers.get("Authorization", ""))
    service = m.group(1) if m else "?"
    target = headers.get("X-Amz-Target")
    if target:  # JSON protocol
        return service, target.split(".")[-1]
    url = urlsplit(path)
    query = parse_qs(url.query, keep_blank_values=True)
    if body and "x-www-form-urlencoded" in headers.get("Content-Type", ""):  # query protocol
        query = parse_qs(body.decode(errors="replace")) | query
    if "Action" in query:
        return service, query["Action"][0]
    if service == "s3":
        if method == "PUT" and headers.get("x-amz-copy-source"):
            return service, "CopyObject"
        return service, s3_action(method, url.path, query)
    return service, "?"


def s3_action(method: str, path: str, query: dict) -> str:
    parts = [p for p in path.split("/") if p]
    verb = S3_VERBS.get(method, method.title())
    if not parts:
        return "ListBuckets" if method == "GET" else verb + "Service"
    if len(parts) == 1:
        if method == "POST" and "delete" in query:
            return "DeleteObjects"
        for key, name in S3_SUBRESOURCES.items():
            if key in query:
                return f"{verb}Bucket{name}"
        return {"GET": "ListObjects", "PUT": "CreateBucket"}.get(method, verb + "Bucket")
    if method == "POST" and "uploads" in query:
        return "CreateMultipartUpload"
    if method == "POST" and "uploadId" in query:
        return "CompleteMultipartUpload"
    if method == "PUT" and "partNumber" in query:
        return "UploadPart"
    return verb + "Object"


def is_write(service: str, action: str, method: str) -> bool:
    if service == "s3":
        return method not in READ_METHODS
    return action.startswith(tuple(WRITE_PREFIXES))


class Subscriber:
    def __init__(self):
        self.queue: queue.Queue = queue.Queue(QUEUE_SIZE)
        self.dropped = threading.Event()
        self.sock: socket.socket | None = None


class EventHub:
    """Fan-out of write events to SSE clients; publishing never blocks the proxy."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: set[Subscriber] = set()
        self._seq = itertools.count(1)

    def subscribe(self) -> Subscriber:
        sub = Subscriber()
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    def publish(self, event: dict) -> dict:
        with self._lock:
            event = {"seq": next(self._seq), **event}
            subscribers = list(self._subscribers)
        for sub in subscribers:
            try:
                sub.queue.put_nowait(event)
            except queue.Full:
                self.drop(sub)
        return event

    def drop(self, sub: Subscriber) -> None:
        self.unsubscribe(sub)
        sub.dropped.set()
        if sub.sock is not None:  # unblock a writer stuck on a full socket buffer
            try:
                sub.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def read_body(rfile, headers) -> bytes:
    """Request body; a chunked upload is reassembled so it can go upstream with Content-Length."""
    if "chunked" in headers.get("Transfer-Encoding", "").lower():
        chunks = []
        while True:
            size = int(rfile.readline().split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while rfile.readline() not in (b"\r\n", b"\n", b""):  # trailers
                    pass
                return b"".join(chunks)
            chunks.append(rfile.read(size))
            rfile.readline()
    return rfile.read(int(headers.get("Content-Length") or 0))


def proxy_handler(upstream: str, hub: EventHub):
    target = urlsplit(upstream)

    class Proxy(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self):
            t0 = time.perf_counter()
            try:
                body = read_body(self.rfile, self.headers)
            except ValueError:  # a chunk size that is not hex
                self.send_error(400, "api-tap: malformed chunked body")
                return
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=120)
            try:
                # skip_host: keep the client's Host header so the SigV4 signature stays valid.
                conn.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
                for k, v in self.headers.items():
                    if k.lower() not in HOP_BY_HOP and k.lower() != "content-length":
                        conn.putheader(k, v)
                if body or self.command in ("POST", "PUT", "PATCH"):
                    conn.putheader("Content-Length", str(len(body)))
                conn.endheaders(body or None)
                resp = conn.getresponse()
                data = resp.read()
            except (OSError, http.client.HTTPException) as e:  # e.g. Floci recreated mid-request by `labctl reset`
                self.send_error(502, f"api-tap: upstream {upstream} unreachable: {e}")
                return
            finally:
                conn.close()
            self.send_response_only(resp.status, resp.reason)
            # A HEAD or 304 answer has no body but its Content-Length describes the object
            # (S3 HeadObject's ContentLength comes from it), so pass it through as is.
            bodiless = self.command == "HEAD" or resp.status in (204, 304)
            for k, v in resp.getheaders():
                if k.lower() not in HOP_BY_HOP and (bodiless or k.lower() != "content-length"):
                    self.send_header(k, v)
            if not bodiless:
                self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            service, action = describe(self.headers, body, self.command, self.path)
            write = is_write(service, action, self.command)
            if resp.status < 400:
                event = {"ts": time.time(), "service": service, "action": action, "status": resp.status, "write": write, "ms": ms}
                if write:
                    hub.publish(event)
            print(f"{service}\t{action}\t{resp.status}\t{'write' if write else 'read'}\t{ms}ms", flush=True)

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_PATCH = _forward

        def log_message(self, *args):
            pass

    return Proxy


def events_handler(upstream: str, hub: EventHub):
    class Events(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # the stream ends when the connection closes

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                ok = upstream_healthy(upstream)
                self.send_response(200 if ok else 503)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok\n" if ok else b"upstream down\n")
            elif path == "/events":
                # Same DNS-rebinding guard as the lab-server: only a loopback Host may read the stream.
                if self.headers.get("Host", "").rsplit(":", 1)[0] not in ("127.0.0.1", "localhost"):
                    self.send_error(403)
                    return
                self.stream()
            else:
                self.send_error(404)

        def stream(self):
            sub = hub.subscribe()
            sub.sock = self.connection
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while not sub.dropped.is_set():
                    try:
                        event = sub.queue.get(timeout=KEEPALIVE_S)
                        self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except OSError:
                pass  # client went away or was dropped
            finally:
                hub.unsubscribe(sub)

        def log_message(self, *args):
            pass

    return Events


def upstream_healthy(upstream: str) -> bool:
    target = urlsplit(upstream)
    conn = http.client.HTTPConnection(target.hostname, target.port, timeout=2)
    try:
        conn.request("GET", HEALTH_PATH)
        return conn.getresponse().status == 200
    except OSError:
        return False
    finally:
        conn.close()


class ApiTap:
    """The proxy and the event stream, each on its own threaded server."""

    def __init__(self, upstream: str, port: int, events_port: int, bind: str = "127.0.0.1"):
        self.hub = EventHub()
        self.proxy = ThreadingHTTPServer((bind, port), proxy_handler(upstream, self.hub))
        self.events = ThreadingHTTPServer((bind, events_port), events_handler(upstream, self.hub))
        for server in (self.proxy, self.events):
            server.daemon_threads = True

    def start(self) -> "ApiTap":
        for server in (self.proxy, self.events):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        return self

    def close(self) -> None:
        for server in (self.proxy, self.events):
            server.shutdown()
            server.server_close()


def main() -> None:
    upstream = os.environ.get("TAP_UPSTREAM", "http://floci:4566")
    port = int(os.environ.get("TAP_PORT", "4566"))
    events_port = int(os.environ.get("TAP_EVENTS_PORT", "4568"))
    tap = ApiTap(upstream, port, events_port, os.environ.get("TAP_BIND", "0.0.0.0")).start()
    print(f"api-tap :{port} -> {upstream}; events on :{events_port}/events", file=sys.stderr, flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        tap.close()


if __name__ == "__main__":
    main()
