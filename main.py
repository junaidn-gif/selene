"""Offline HTTP API and dashboard, using only Python's standard library."""
import json, threading, time, webbrowser, argparse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from simulation import Simulation, compare, MODES
sim=Simulation(); running=False; lock=threading.RLock()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send_json(self,data,status=200):
        payload=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        with lock:
            endpoints={'/state':lambda:dict(sim.state(),running=running),'/history':lambda:sim.history,'/metrics':sim.kpis,'/decisions':lambda:sim.decisions}
            if self.path in endpoints:return self.send_json(endpoints[self.path]())
        if self.path in ('/','/index.html'):
            body=Path(__file__).with_name('static').joinpath('index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        else:self.send_json({'error':'Not found'},404)
    def do_POST(self):
        global sim,running
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>4096:raise ValueError('Request too large')
            body=json.loads(self.rfile.read(size) or b'{}')
            if self.path=='/compare':
                with lock:events=list(sim.events)
                return self.send_json(compare(events))
            with lock:
                if self.path=='/reset':sim=Simulation(sim.mode);running=False
                elif self.path=='/start':running=not sim.state()['complete']
                elif self.path=='/pause':running=False
                elif self.path=='/step':running=False;sim.step()
                elif self.path=='/mode':
                    mode=body.get('mode')
                    if mode not in MODES:raise ValueError('Unknown mode')
                    # Reset to preserve a meaningful independent run; retain injected scenario.
                    sim=Simulation(mode,sim.events);running=False
                elif self.path=='/fault':sim.inject(body.get('fault'))
                else:return self.send_json({'error':'Not found'},404)
                return self.send_json(dict(sim.state(),running=running))
        except (ValueError,TypeError,AttributeError) as exc:self.send_json({'error':str(exc)},400)
def clock():
    global running
    while True:
        time.sleep(.25)
        with lock:
            if running:
                for _ in range(2):sim.step()
                if sim.state()['complete']:running=False
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    threading.Thread(target=clock,daemon=True).start()
    url=f'http://127.0.0.1:{args.port}';print('SELENE running at '+url+' — Ctrl+C to stop')
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
