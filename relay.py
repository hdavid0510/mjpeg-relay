#!/usr/bin/env python3

import sys
import os
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
	"""HTTP Handlers"""
	store: FrameStore = request.app['store']
	boundary = "frame"
	headers = {
		"Content-Type": f"multipart/x-mixed-replace; boundary=--{boundary}"
	}
	async def frame_generator():
		while True:
			frame = await store.subscribe()
			yield f"--{boundary}\r\n".encode()
			yield b"Content-Type: image/jpeg\r\n"
			yield f"Content-Length: {len(frame)}\r\n\r\n".encode()
			yield frame + b"\r\n"
	return web.Response(body=frame_generator(), headers=headers)

async def snapshot(request):
	store: FrameStore = request.app['store']
	frame = store._frame
	if not frame:
		raise web.HTTPNotFound(text="No frame available yet")
	return web.Response(body=frame, content_type='image/jpeg')

async def websocket_feed(request):
	store: FrameStore = request.app['store']
	ws = web.WebSocketResponse()
	await ws.prepare(request)
	try:
		while True:
			frame = await store.subscribe()
			await ws.send_bytes(frame)
	except asyncio.CancelledError:
		pass
	finally:
		await ws.close()
	return ws

# 
def parse_cli():
	"""CLI Parsing"""
	p = argparse.ArgumentParser(
		description="High-efficiency MJPEG relay (asyncio + aiohttp)"
	)
	p.add_argument("source_url", nargs="?", default=os.environ.get("SOURCE_URL"),
					help="URL of the MJPEG source stream (or set SOURCE_URL env)")
	p.add_argument("-p", "--port",   type=int, default=54321,
					help="HTTP port for relayed MJPEG")
	p.add_argument("-w", "--wsport", type=int, default=54322,
					help="WebSocket port for binary frames")
	args = p.parse_args()
	if not args.source_url:
		p.print_help()
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
	app['store'] = store
	app.add_routes([
		web.get('/stream', mjpeg_stream),
		web.get('/snapshot', snapshot),
		web.get('/ws', websocket_feed),
	])

	runner = web.AppRunner(app)
	await runner.setup()

	# two listeners (HTTP and WS share same app)
	site1 = web.TCPSite(runner, '0.0.0.0', args.port)
	site2 = web.TCPSite(runner, '0.0.0.0', args.wsport)
	await site1.start()
	await site2.start()

	print(f"↪ HTTP MJPEG on http://0.0.0.0:{args.port}/stream")
	print(f"↪ Snapshot   on http://0.0.0.0:{args.port}/snapshot")
	print(f"↪ WebSocket  on ws://0.0.0.0:{args.wsport}/ws")

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
