#!/usr/bin/env python3

import sys
import os
import types
import time
import argparse
import asyncio
import aiohttp
from aiohttp import web


class FrameStore:
	"""FrameStore holds only the latest frame and notifies subscribers on update."""
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


async def fetch_loop(source_url: str, store: FrameStore, feedlost: bytes):
	"""
	Continuously attempt to fetch the MJPEG source. 
	If the source is unreachable or an error occurs, repeatedly push `feedlost` frames every second.
	When the source is back, resume normal frame parsing.
	"""
	while True:
		try:
			# Try to connect to MJPEG source
			session_timeout = aiohttp.ClientTimeout(total=None)
			async with aiohttp.ClientSession(timeout=session_timeout) as session:
				async with session.get(source_url) as resp:
					if resp.status != 200:
						raise aiohttp.ClientError(f"HTTP {resp.status}")

					# When connection succeeds, read chunks and parse JPEG frames
					buffer = bytearray()
					async for chunk in resp.content.iter_chunked(1024):
						buffer.extend(chunk)
						# find JPEG start/end markers
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
					# If the loop ends normally, it means the connection closed; raise to trigger fallback
					raise aiohttp.ClientError("Connection closed unexpectedly")
		except Exception:
			# Any exception means we lost the feed. Push feedlost image until we can reconnect.
			while True:
				try:
					# Push the feedlost image
					await store.update(feedlost)
				except Exception:
					pass
				# Wait 1 second before trying again
				await asyncio.sleep(1)
				# Test reconnect by attempting a HEAD request (fast check)
				try:
					async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as test_sess:
						async with test_sess.head(source_url) as test_resp:
							if test_resp.status == 200:
								# source is back; break out to outer loop to re-enter stream parsing
								break
				except Exception:
					continue
			# Now re-loop to attempt full GET again


async def mjpeg_stream(request):
	"""Handle HTTP MJPEG stream, track per-client outbound bytes."""
	store: FrameStore = request.app.state.store
	boundary = "frame"
	headers = {
		"Content-Type": f"multipart/x-mixed-replace; boundary=--{boundary}"
	}
	ip = request.remote or "unknown"
	now = time.time()

	clients = request.app.state.clients
	# On connect: if first time, create entry; otherwise bump count and clear offline_since
	if ip not in clients:
		clients[ip] = {
			"since": now,        # when this IP first ever connected
			"bytes_sent": 0,     # total accumulated bytes to this IP
			"count": 1,          # reference count of active connections
			"offline_since": None  # marked when count drops to 0
		}
	else:
		clients[ip]["count"] += 1
		clients[ip]["offline_since"] = None  # client is back online

	async def frame_generator():
		try:
			while True:
				frame = await store.subscribe()
				part = (
					f"--{boundary}\r\n".encode() +
					b"Content-Type: image/jpeg\r\n" +
					f"Content-Length: {len(frame)}\r\n\r\n".encode() +
					frame +
					b"\r\n"
				)
				# update global total and per-client total
				request.app.state.bytes_sent += len(part)
				clients[ip]["bytes_sent"] += len(part)
				yield part
		except asyncio.CancelledError:
			raise
		finally:
			# On disconnect: decrement count. If zero, mark offline but do not remove.
			if ip in clients:
				clients[ip]["count"] -= 1
				if clients[ip]["count"] <= 0:
					clients[ip]["offline_since"] = time.time()

	return web.Response(body=frame_generator(), headers=headers)


async def snapshot(request):
	"""Return the most recent JPEG frame (snapshot)"""
	store: FrameStore = request.app.state.store
	frame = store._frame
	if not frame:
		raise web.HTTPNotFound(text="No frame available yet")
	return web.Response(body=frame, content_type='image/jpeg')


async def websocket_feed(request):
	"""WebSocket handler (binary frames) with per-client tracking"""
	store: FrameStore = request.app.state.store
	ws = web.WebSocketResponse()
	await ws.prepare(request)

	ip = request.remote or "unknown"
	now = time.time()

	clients = request.app.state.clients
	if ip not in clients:
		clients[ip] = {
			"since": now,
			"bytes_sent": 0,
			"count": 1,
			"offline_since": None
		}
	else:
		clients[ip]["count"] += 1
		clients[ip]["offline_since"] = None

	try:
		while True:
			frame = await store.subscribe()
			await ws.send_bytes(frame)
			request.app.state.bytes_sent += len(frame)
			clients[ip]["bytes_sent"] += len(frame)
	except asyncio.CancelledError:
		# client closed connection
		pass
	finally:
		# On disconnect: decrement count, mark offline if zero
		if ip in clients:
			clients[ip]["count"] -= 1
			if clients[ip]["count"] <= 0:
				clients[ip]["offline_since"] = time.time()
		await ws.close()

	return ws


async def status_report(request):
	"""Return JSON status including every client (online or offline)"""
	app = request.app

	now         = time.time()
	total_bytes = app.state.bytes_sent

	# Compute instantaneous bps by diffing against previous snapshot
	prev_bytes  = app.state.prev_bytes
	prev_time   = app.state.prev_time
	delta_bytes = total_bytes - prev_bytes
	delta_time  = now - prev_time if now>prev_time else 1.0
	inst_bps    = delta_bytes / delta_time

	# Update prev_bytes and prev_time for next call
	app.state.prev_bytes = total_bytes
	app.state.prev_time  = now

	# Build client list
	clients_dict = app.state.clients  # dict[ip] → {since, bytes_sent, count, offline_since}

	client_list = []
	for ip, info in clients_dict.items():
		client_list.append({
			"ip":             ip,
			"since":          info["since"],           # raw UNIX timestamp (seconds)
			"outbound_bytes": info["bytes_sent"],      # accumulated bytes from this IP
			"online":         (info["count"] > 0),     # True if currently connected
			"offline_since":  info["offline_since"]    # raw UNIX timestamp or None
		})

	payload = {
		"uptime":        now - app.state.start_time, # raw seconds
		"inbound_bytes": total_bytes,
		"inbound_bps":   inst_bps,                   # instantaneous rate (bytes/sec)
		"clients":       client_list                 # all clients ever seen during this run
	}
	return web.json_response(payload)


async def dashboard(request):
	"""Serve dashboard.html verbatim"""
	html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
	try:
		text = open(html_path, "r", encoding="utf-8").read()
	except Exception:
		raise web.HTTPNotFound(text="dashboard.html not found")
	return web.Response(body=text, content_type="text/html")


async def restart_relay(request):
	"""Exit the process so that Docker can restart the container."""
	loop = asyncio.get_event_loop()
	loop.call_later(0.1, lambda: os._exit(0))
	print("Received restart request.")
	return web.Response(text="Restarting relay...", content_type="text/plain")


def parse_cli():
	"""Parse CLI args; shrink traceback if no SOURCE_URL is given"""
	parser = argparse.ArgumentParser(
		description="High-efficiency MJPEG relay (asyncio + aiohttp)"
	)

	def get_env_port(env: str, default: int):
		try:
			port = int(os.environ.get(env))
		except (ValueError, TypeError):
			return default
		return port if 1 <= port < 65536 else default

	parser.add_argument(
		"source_url",
		nargs="?",
		default=os.environ.get("SOURCE_URL"),
		help="URL of MJPEG source stream (or set SOURCE_URL env)"
	)
	parser.add_argument(
		"-p", "--port",
		type=int,
		default=get_env_port("PORT", 54321),
		help="HTTP port for MJPEG + dashboard"
	)
	parser.add_argument(
		"-w", "--wsport",
		type=int,
		default=get_env_port("WSPORT", 54322),
		help="WebSocket port"
	)
	args = parser.parse_args()
	if not args.source_url:
		parser.print_help()
		sys.exit(1)
	return args


async def main():
	args = parse_cli()

	# Optional: use uvloop if installed
	try:
		import uvloop
		uvloop.install()
	except ImportError:
		pass

	# Load the “feed lost” JPEG into memory
	static_dir = os.path.join(os.path.dirname(__file__), "static")
	feedlost_path = os.path.join(static_dir, "feedlost.jpeg")
	try:
		with open(feedlost_path, "rb") as f:
			feedlost_bytes = f.read()
	except FileNotFoundError:
		print("ERROR: static/feedlost.jpeg not found. Exiting.")
		sys.exit(1)

	# Initialize FrameStore and start fetch loop
	store = FrameStore()
	fetch_task = asyncio.create_task(fetch_loop(args.source_url, store, feedlost_bytes))

	# Build aiohttp app and put all mutable state on app.state
	app = web.Application()
	app.state = types.SimpleNamespace()
	app.state.store      = store
	app.state.clients    = {}
	app.state.start_time = time.time()
	app.state.prev_time  = app.state.start_time
	app.state.bytes_sent = 0
	app.state.prev_bytes = 0

	app.add_routes([
		web.get('/stream', mjpeg_stream),
		web.get('/snapshot', snapshot),
		web.get('/ws', websocket_feed),
		web.get('/status', status_report),
		web.get('/dashboard', dashboard),
		web.post('/restart', restart_relay),
	])

	app.router.add_static('/static/', static_dir, show_index=False)

	# Catch-all redirect -> /dashboard
	async def catch_all_redirect(request):
		raise web.HTTPFound("/dashboard")
	app.router.add_get("/{tail:.*}", catch_all_redirect)

	runner = web.AppRunner(app)
	await runner.setup()

	listener_http      = web.TCPSite(runner, '0.0.0.0', args.port)
	listener_websocket = web.TCPSite(runner, '0.0.0.0', args.wsport)
	await listener_http.start()
	await listener_websocket.start()

	print(f"HTTP MJPEG on http://0.0.0.0:{args.port}/stream")
	print(f"Snapshot   on http://0.0.0.0:{args.port}/snapshot")
	print(f"WebSocket  on   ws://0.0.0.0:{args.wsport}/ws")
	print(f"Stat JSON  on http://0.0.0.0:{args.port}/status")
	print(f"Dashboard  on http://0.0.0.0:{args.port}/dashboard")

	await fetch_task


if __name__ == '__main__':
	# very short tracebacks: only exception message
	sys.tracebacklimit = 0
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		print("Shutting down...")
		sys.exit(0)
