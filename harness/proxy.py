"""Log request bodies on their way to vLLM: proxy.py <port> <logdir>"""
import http.client, itertools, os, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = urllib.parse.urlsplit(os.environ.get("VLLM_URL", "http://spark1:8000")).netloc.split(":")
counter = itertools.count()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with open(os.path.join(sys.argv[2], f"{next(counter):03d}.json"), "wb") as f:
            f.write(body)
        self._forward("POST", body)

    def do_GET(self):
        self._forward("GET", None)

    def _forward(self, method, body):
        conn = http.client.HTTPConnection(UPSTREAM[0], int(UPSTREAM[1]), timeout=3600)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}
        conn.request(method, self.path, body=body, headers=headers)
        resp = conn.getresponse()
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in ("transfer-encoding", "content-length", "connection"):
                self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        while chunk := resp.read1(65536):
            self.wfile.write(chunk)
            self.wfile.flush()

    def log_message(self, *args):
        pass


os.makedirs(sys.argv[2], exist_ok=True)
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
