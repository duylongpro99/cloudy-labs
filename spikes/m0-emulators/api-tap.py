#!/usr/bin/env python3
"""Minimal pass-through reverse proxy for AWS CLI traffic (stdlib only).

Usage: python3 api-tap.py [--port 4580] [--upstream http://localhost:4566]
Forwards method, path, headers (including Host and Authorization) and body unchanged,
then logs one line per request: service, action, status, upstream ms, total ms.
"""
import argparse
import http.client
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HOP_BY_HOP = {"connection", "keep-alive", "proxy-connection", "transfer-encoding", "upgrade", "te", "trailer"}
SCOPE = re.compile(r"Credential=[^/]+/\d+/[^/]+/([^/]+)/aws4_request")


def describe(headers, body: bytes):
    m = SCOPE.search(headers.get("Authorization", ""))
    service = m.group(1) if m else "?"
    target = headers.get("X-Amz-Target")
    if target:
        return service, target.split(".")[-1]
    if body and "x-www-form-urlencoded" in headers.get("Content-Type", ""):
        return service, parse_qs(body.decode(errors="replace")).get("Action", ["?"])[0]
    return service, "?"


def make_handler(upstream):
    target = urlsplit(upstream)

    class Tap(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self):
            t0 = time.perf_counter()
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=120)
            # skip_host: keep the client's Host header so the SigV4 signature stays valid.
            conn.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
            for k, v in headers.items():
                conn.putheader(k, v)
            conn.endheaders(body or None)
            t1 = time.perf_counter()
            resp = conn.getresponse()
            data = resp.read()
            t2 = time.perf_counter()
            self.send_response_only(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in HOP_BY_HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
            service, action = describe(self.headers, body)
            print(f"{service}\t{action}\t{resp.status}\tupstream={(t2 - t1) * 1000:.1f}ms\ttotal={(time.perf_counter() - t0) * 1000:.1f}ms",
                  flush=True)

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_PATCH = _forward

        def log_message(self, *args):
            pass

    return Tap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4580)
    ap.add_argument("--upstream", default="http://localhost:4566")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.upstream))
    print(f"api-tap listening on :{args.port} -> {args.upstream}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
