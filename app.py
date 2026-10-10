"""Local app server. Whisper starts only after the user presses Transcribe."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import local_transcribe as engine
import local_runtime as runtime

ROOT = Path(__file__).resolve().parent
runtime.configure_environment()
DATA = runtime.data_directory()
DATA.mkdir(parents=True, exist_ok=True)
runtime.migrate_legacy_queue(DATA)
TOKEN = secrets.token_urlsafe(32)


class Controller:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.worker = None
        self.stop = threading.Event()
        saved = DATA / 'queue.json'
        self.data = json.loads(saved.read_text()) if saved.exists() else {
            'output': str(Path.home() / 'Downloads/LocalTranscribe Output'), 'jobs': []}
        for job in self.data['jobs']:
            if job['status'] in ('Transcribing', 'Queued'):
                job['status'] = 'Stopped'
        self.save()

    def save(self):
        engine.save_json(DATA / 'queue.json', self.data)

    def snapshot(self):
        with self.lock:
            return {**self.data, 'active': bool(self.worker and self.worker.is_alive()),
                    'jobs': [dict(job) for job in self.data['jobs']]}

    def add(self, paths):
        expanded = []
        for supplied in paths:
            path = Path(supplied).expanduser().resolve(strict=True)
            expanded.extend(sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in engine.MEDIA_EXTENSIONS)
                            if path.is_dir() else [path])
        with self.lock:
            existing = {job['path'] for job in self.data['jobs']}
            for path in expanded:
                if str(path) in existing:
                    continue
                info = engine.probe(path)
                self.data['jobs'].append({'id': hashlib.sha256(str(path).encode()).hexdigest()[:16],
                    'name': path.name, 'path': str(path), 'bytes': info['source']['bytes'],
                    'duration': info['duration_seconds'], 'status': 'Ready', 'progress': 0,
                    'error': None, 'output_folder': None})
                existing.add(str(path))
            self.save()

    def start(self, ids):
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError('A transcription is already running. Stop it before starting another selection.')
            selected = [job for job in self.data['jobs'] if job['id'] in ids]
            if not selected:
                raise ValueError('Select at least one recording.')
            self.stop.clear()
            for job in selected:
                job.update(status='Queued', error=None)
            self.save()
            self.worker = threading.Thread(target=self.run, args=(selected,), daemon=True)
            self.worker.start()

    def run(self, selected):
        try:
            for job in selected:
                if self.stop.is_set():
                    break
                with self.lock:
                    output = Path(self.data['output']).expanduser().resolve()
                    output.mkdir(parents=True, exist_ok=True)
                    job.update(status='Transcribing', output_folder=str(output / Path(job['path']).stem))
                    self.save()
                    command = ['/usr/bin/caffeinate', '-i', str(runtime.python_executable()), '-s', str(ROOT / 'local_transcribe.py'),
                               'run', job['path'], '--output', str(output)]
                    self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                    text=True, bufsize=1, start_new_session=True)
                    process = self.process
                logs = DATA / 'logs'
                logs.mkdir(exist_ok=True)
                with (logs / (job['id'] + '.log')).open('a') as log:
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        with self.lock:
                            if item.get('event') == 'chunk_complete':
                                job['progress'] = item['percent']
                            if item.get('event') in ('failed', 'file_error'):
                                job['error'] = item.get('error')
                            self.save()
                code = process.wait()
                with self.lock:
                    self.process = None
                    job['status'] = 'Stopped' if self.stop.is_set() or code == 130 else 'Complete' if code == 0 else 'Failed'
                    if code == 0:
                        job['progress'] = 100
                    elif not job['error'] and job['status'] == 'Failed':
                        job['error'] = 'Transcription failed. See this recording’s local log for details.'
                    self.save()
        except Exception as error:
            with self.lock:
                job.update(status='Failed', error=str(error))
                self.save()
        finally:
            with self.lock:
                for job in selected:
                    if job['status'] == 'Queued':
                        job['status'] = 'Ready'
                self.save()

    def cancel(self):
        with self.lock:
            self.stop.set()
            if self.process and self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGINT)


controller = Controller()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, value, code=200):
        payload = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.valid_host():
            return self.reply({'error': 'Local access only'}, 403)
        if self.path == '/health':
            return self.reply({'app': 'LocalTranscribe', 'root': str(ROOT)})
        if self.path == '/api/state':
            return self.reply(controller.snapshot())
        if self.path != '/':
            return self.reply({'error': 'Not found'}, 404)
        payload = (ROOT / 'ui/index.html').read_text().replace('__TOKEN__', TOKEN).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-LocalTranscribe-Token') != TOKEN:
            return self.reply({'error': 'Open the local app to perform this action'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 65536:
                raise ValueError('Only file paths are accepted. Video files are read directly from disk.')
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/add':
                controller.add(body['paths'])
            elif self.path == '/api/start':
                controller.start(body['ids'])
            elif self.path == '/api/stop':
                controller.cancel()
            elif self.path == '/api/output':
                with controller.lock:
                    if controller.snapshot()['active']:
                        raise ValueError('Stop the current run before changing the output folder.')
                    controller.data['output'] = str(Path(body['path']).expanduser().resolve())
                    controller.save()
            elif self.path == '/api/remove':
                with controller.lock:
                    if controller.snapshot()['active']:
                        raise ValueError('Stop the current run before removing recordings from the list.')
                    controller.data['jobs'] = [job for job in controller.data['jobs'] if job['id'] != body['id']]
                    controller.save()
            elif self.path == '/api/reveal':
                with controller.lock:
                    job = next((job for job in controller.data['jobs'] if job['id'] == body.get('id')), None)
                    path = Path(job['output_folder'] if job and job['output_folder'] else controller.data['output'])
                if not path.is_dir():
                    raise ValueError('This output folder will be created when you start a transcription.')
                subprocess.Popen(['open', str(path)])
            else:
                return self.reply({'error': 'Not found'}, 404)
            self.reply(controller.snapshot())
        except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as error:
            self.reply({'error': str(error)}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8789)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    shutdown = threading.Event()
    def stop(_signal, _frame):
        controller.cancel()
        shutdown.set()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        shutdown.wait()
    finally:
        controller.cancel()
        if controller.worker:
            controller.worker.join(timeout=8)
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
