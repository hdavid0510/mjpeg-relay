#!/usr/bin/env python3

import sys
import os
import time
from datetime import datetime, timedelta
import argparse
import asyncio
import aiohttp
from aiohttp import web


class FrameStore:
	"""FrameStore holds only the latest frame and notifies subscribers on update"""
	def __init__(self):
		self._frame = None
		self._cond = asyncio.Condition()

	async def update(self, frame: bytes):
		async with self._cond:
			self._frame = frame
			self._cond.notify_all()

	async def subscribe(self) -> bytes:
		async with self._cond:
			await self._cond.wait()
			return self._frame


async def fetch_loop(source_url: str, store: FrameStore):
	"""Fetch MJPEG stream, parse JPEG frames, push to FrameStore"""
	session_timeout = aiohttp.ClientTimeout(total=None)
	async with aiohttp.ClientSession(timeout=session_timeout) as session:
		async with session.get(source_url) as resp:
			buffer = bytearray()
			async for chunk in resp.content.iter_chunked(1024):
				buffer.extend(chunk)
				# find JPEG start and end markers
				while True:
					start = buffer.find(b'\xff\xd8')
					end   = buffer.find(b'\xff\xd9')
					if start != -1 and end != -1 and end > start:
						frame = bytes(buffer[start:end+2])
						# remove up to end
						del buffer[:end+2]
						# push to store
						await store.update(frame)
					else:
						break

async def mjpeg_stream(request):
	"""Handle HTTP MJPEG stream, track per-client outbound bytes"""
	store: FrameStore = request.app.state.store
	boundary = "frame"
	headers = {
		"Content-Type": f"multipart/x-mixed-replace; boundary=--{boundary}"
	}
	ip = request.remote or "unknown"
	now = time.time()

	clients = request.app.state.clients
	# On connect: create or bump the ref‐count
	if ip not in clients:
		clients[ip] = {
			"since": now,
			"bytes_sent": 0,
			"count": 1
		}
	else:
		clients[ip]["count"] += 1

	async def frame_generator():
		try:
			while True:
				frame = await store.subscribe()
				# build one chunk per frame
				part = (
					f"--{boundary}\r\n".encode() +
					b"Content-Type: image/jpeg\r\n" +
					f"Content-Length: {len(frame)}\r\n\r\n".encode() +
					frame +
					b"\r\n"
				)
				# global total bytes
				request.app.state.bytes_sent += len(part)
				# per‐IP bytes
				clients[ip]["bytes_sent"] += len(part)
				yield part
		except asyncio.CancelledError:
			raise
		finally:
			# On disconnect: decrement count, and only pop if it hits zero
			if ip in clients:
				clients[ip]["count"] -= 1
				if clients[ip]["count"] <= 0:
					clients.pop(ip, None)

	return web.Response(body=frame_generator(), headers=headers)

async def snapshot(request):
	"""Handle single frame"""
	store: FrameStore = request.app.state.store
	frame = store._frame
	if not frame:
		raise web.HTTPNotFound(text="No frame available yet")
	return web.Response(body=frame, content_type='image/jpeg')

async def websocket_feed(request):
	"""WebSocket handler with per-client tracking"""
	store: FrameStore = request.app.state.store
	ws = web.WebSocketResponse()
	await ws.prepare(request)

	ip = request.remote or "unknown"
	now = time.time()

	clients = request.app.state.clients
	# On connect: create or bump the ref‐count
	if ip not in clients:
		clients[ip] = {
			"since": now,
			"bytes_sent": 0,
			"count": 1
		}
	else:
		clients[ip]["count"] += 1

	try:
		while True:
			frame = await store.subscribe()
			await ws.send_bytes(frame)
			# global total bytes
			request.app.state.bytes_sent += len(frame)
			# per‐IP bytes
			clients[ip]["bytes_sent"] += len(frame)
	except asyncio.CancelledError:
		pass
	finally:
		# On disconnect: decrement count, and only pop if it hits zero
		if ip in clients:
			clients[ip]["count"] -= 1
			if clients[ip]["count"] <= 0:
				clients.pop(ip, None)
		await ws.close()

	return ws

async def status_report(request):
	"""Return JSON status"""
	app = request.app
	elapsed = time.time() - app['start_time']
	total_bytes = app['bytes_sent']
	avg_bps = (total_bytes / elapsed) if elapsed > 0 else 0.0
	clients = app['clients']

	# Build list of client dicts
	connected_list = []
	for ip, info in clients.items():
		connected_list.append({
			"ip": ip,
			"since": info["since"],
			"sent": info["bytes_sent"]
		})

	payload = {
		"uptime": elapsed,
		"received": total_bytes,
		"bandwidth": avg_bps,
		"connection_count": len(connected_list),
		"connection": connected_list
	}
	return web.json_response(payload)

async def dashboard(request):
	"""Read dashboard.html from disk and return it"""
	html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
	try:
		text = open(html_path, "r", encoding="utf-8").read()
	except Exception:
		raise web.HTTPNotFound(text="dashboard.html not found")
	return web.Response(body=text, content_type="text/html")

async def catch_all_redirect(request):
	"""Always redirect to /dashboard for any unmatched path"""
	raise web.HTTPFound("/dashboard")


def parse_cli():
	"""Parse arguments from CLI"""
	parser = argparse.ArgumentParser(
		description="High-efficiency MJPEG relay (asyncio + aiohttp)"
	)

	def get_env_port(env:str, default:int):
		try:
			port = int(os.environ.get(env))
		except (ValueError, TypeError):
			return default
		return port if 1<=port<65536 else default
	
	parser.add_argument("source_url", nargs="?", default=os.environ.get("SOURCE_URL"),
					help="URL of the MJPEG source stream (or set SOURCE_URL env)")
	parser.add_argument("-p", "--port",   type=int, default=get_env_port("PORT", 54321),
					help="HTTP port for relayed MJPEG")
	parser.add_argument("-w", "--wsport", type=int, default=get_env_port("WSPORT", 54322),
					help="WebSocket port for binary frames")
	args = parser.parse_args()
	if not args.source_url:
		parser.print_help()
		sys.exit(1)
	return args


async def main():
	args = parse_cli()

	# optional speed boost
	try:
		import uvloop
		uvloop.install()
	except ImportError:
		pass

	store = FrameStore()

	# start fetch loop
	fetch_task = asyncio.create_task(fetch_loop(args.source_url, store))

	# setup web server
	app = web.Application()
	app.state.store = store
	app.state.clients = {}       # dict[ip] → {"since": <epoch>, "bytes_sent": <int>}
	app.state.bytes_sent = 0     # total bytes sent (since start)
	app.state.start_time = time.time()

	app.add_routes([
		web.get('/stream', mjpeg_stream),
		web.get('/snapshot', snapshot),
		web.get('/ws', websocket_feed),
		web.get('/status', status_report),
		web.get('/dashboard', dashboard),
	])

	# Serve anything under /static/ from the local ./static folder
	static_folder = os.path.join(os.path.dirname(__file__), "static")
	app.router.add_static('/static/', static_folder, show_index=False)
	app.router.add_get("/{tail:.*}", catch_all_redirect)

	runner = web.AppRunner(app)
	await runner.setup()
	listener_http = web.TCPSite(runner, '0.0.0.0', args.port)
	listener_websocket = web.TCPSite(runner, '0.0.0.0', args.wsport)
	await listener_http.start()
	await listener_websocket.start()

	print(f"HTTP MJPEG on http://0.0.0.0:{args.port}/stream")
	print(f"Snapshot   on http://0.0.0.0:{args.port}/snapshot")
	print(f"WebSocket  on ws://0.0.0.0:{args.wsport}/ws")
	print(f"Stat JSON  on http://0.0.0.0:{args.port}/status")
	print(f"Dashboard  on http://0.0.0.0:{args.port}/dashboard")

	# keep running until cancelled
	await fetch_task


if __name__ == '__main__':
	# very short tracebacks: only exception message
	sys.tracebacklimit = 0
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		print("Shutting down...")
		sys.exit(0)
