#!/usr/bin/env python3
"""One JSON command against a running TG2Recomp debug server."""
import argparse
import json
import socket
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('command')
p.add_argument('--port', type=int, default=4400)
p.add_argument('--args', default='{}', help='JSON object of command arguments')
a = p.parse_args()
with socket.create_connection(('127.0.0.1', a.port), timeout=5) as s:
    s.sendall((json.dumps(dict(json.loads(a.args), id=1, cmd=a.command)) + '\n').encode())
    print(s.makefile().readline().strip())
