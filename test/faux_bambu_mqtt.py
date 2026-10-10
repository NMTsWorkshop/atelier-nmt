"""Un faux P1S côté MQTT : il n'accepte qu'une forme d'adresse, comme le
vrai, et répond FAIL aux autres. C'est ce qui permet de vérifier que le
relais essaie les formes connues au lieu d'en parier une."""

import json
import os
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time


def _lg(n):
    b = b""
    while True:
        d, n = n % 128, n // 128
        b += bytes([d | 128 if n else d])
        if not n:
            return b


def _txt(s):
    s = s.encode()
    return struct.pack(">H", len(s)) + s


def _recv(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise EOFError
        b += c
    return b


def _paquet(s):
    e = _recv(s, 1)[0]
    m, v = 1, 0
    while True:
        x = _recv(s, 1)[0]
        v += (x & 127) * m
        m *= 128
        if not x & 128:
            break
    return e >> 4, _recv(s, v)


class FauxBambuMqtt:
    def __init__(self, accepte=None, serie="01P0", port=0):
        self.accepte = accepte
        self.serie = serie
        self.vues = []
        self.etat = "IDLE"
        d = tempfile.mkdtemp()
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048",
                        "-nodes", "-keyout", os.path.join(d, "k.pem"),
                        "-out", os.path.join(d, "c.pem"), "-days", "2",
                        "-subj", "/CN=bambu"], capture_output=True)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(os.path.join(d, "c.pem"), os.path.join(d, "k.pem"))
        self.ctx = ctx
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", port))
        self.srv.listen(8)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._boucle, daemon=True).start()

    def _boucle(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            try:
                c = self.ctx.wrap_socket(c, server_side=True)
            except Exception:
                continue
            threading.Thread(target=self._session, args=(c,), daemon=True).start()

    def _session(self, c):
        try:
            _paquet(c)
            c.sendall(bytes([0x20, 2, 0, 0]))
            while True:
                t, b = _paquet(c)
                if t == 8:
                    c.sendall(bytes([0x90, 3, 0, 1, 0]))
                elif t == 3:
                    lg = struct.unpack(">H", b[:2])[0]
                    pr = json.loads(b[2 + lg:].decode()).get("print", {})
                    self.vues.append(pr.get("url"))
                    bon = (self.accepte is None or pr.get("url") == self.accepte)
                    if bon:
                        self.etat = "RUNNING"
                    rep = {"print": {"command": "project_file",
                                     "result": "SUCCESS" if bon else "FAIL",
                                     "sequence_id": pr.get("sequence_id")}}
                    if not bon:
                        rep["print"]["reason"] = "invalid url"
                    ch = json.dumps(rep).encode()
                    pub = _txt("device/%s/report" % self.serie) + ch
                    c.sendall(bytes([0x30]) + _lg(len(pub)) + pub)
        except Exception:
            pass
        finally:
            try:
                c.close()
            except Exception:
                pass
