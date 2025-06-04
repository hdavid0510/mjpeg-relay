function pad(n) { return n < 10 ? "0" + n : n; }

function formatHMS(totalSeconds) {
	// Convert raw seconds → "H:MM:SS"
	totalSeconds = Math.floor(totalSeconds);
	const hh = pad(Math.floor(totalSeconds / 3600));
	const mm = pad(Math.floor((totalSeconds % 3600) / 60));
	const ss = pad(totalSeconds % 60);
	return `${hh}:${mm}:${ss}`;
}

function formatTimestamp(epochSec) {
	// raw epoch (seconds) → "YYYY-MM-DD HH:MM:SS"
	const date = new Date(epochSec * 1000);
	const yyyy = date.getFullYear();
	const MM = pad(date.getMonth() + 1);
	const dd = pad(date.getDate());
	const HH = pad(date.getHours());
	const mm = pad(date.getMinutes());
	const ss = pad(date.getSeconds());
	return `${yyyy}-${MM}-${dd} ${HH}:${mm}:${ss}`;
}

function humanBytes(bytes) {
	if (bytes < 1024) return bytes + " B";
	const units = ["KB", "MB", "GB", "TB"];
	let u = -1;
	let b = bytes;
	do {
		b /= 1024;
		u++;
	} while (b >= 1024 && u < units.length - 1);
	return b.toFixed(2) + " " + units[u];
}

function humanBps(bps) {
	// Convert bytes/sec → bits/sec → K/M/G/Tbps
	let bits = bps * 8;
	if (bits < 1e3) return bits.toFixed(2) + " bps";
	const units = ["Kbps", "Mbps", "Gbps", "Tbps"];
	let u = -1;
	let v = bits;
	do {
		v /= 1000;
		u++;
	} while (v >= 1000 && u < units.length - 1);
	return v.toFixed(2) + " " + units[u];
}

function fetchStatus() {
	fetch('/status')
		.then(response => response.json())
		.then(data => {
			document.getElementById('uptime').textContent = formatHMS(data.uptime);
			document.getElementById('received').textContent = humanBytes(data.inbound_bytes);
			document.getElementById('bandwidth').textContent = humanBps(data.inbound_bps);
			const onlineCount = data.clients.filter(c => c.online).length;
			document.getElementById('connection_count').textContent = onlineCount;


			const tbody = document.getElementById('client_table_body');
			tbody.innerHTML = ''; // clear existing
			if (!data.clients || data.clients.length === 0) {
				const row = document.createElement('tr');
				const cell = document.createElement('td');
				cell.colSpan = 4;
				cell.textContent = 'No clients connected yet';
				row.appendChild(cell);
				tbody.appendChild(row);
			} else {
				data.clients.forEach(client => {
					const row = document.createElement('tr');
					// If offline, add the "offline" CSS class
					if (!client.online) {
						row.classList.add('offline');
					}

					const ipCell = document.createElement('td');
					ipCell.textContent = client.ip;

					const sentCell = document.createElement('td');
					sentCell.textContent = humanBytes(client.outbound_bytes);

					const connectedCell = document.createElement('td');
					connectedCell.textContent = formatTimestamp(client.since);

					const disconnectedCell = document.createElement('td');
					if (client.offline_since) {
						disconnectedCell.textContent = formatTimestamp(client.offline_since);
					} else {
						disconnectedCell.textContent = '';
					}

					row.appendChild(ipCell);
					row.appendChild(sentCell);
					row.appendChild(connectedCell);
					row.appendChild(disconnectedCell);
					tbody.appendChild(row);
				});
			}

			// Last updated (browser local time)
			const now = new Date();
			document.getElementById('last_updated').textContent = now.toLocaleString();
		})
		.catch(err => {
			console.error('Error fetching /status:', err);
		});
}

// Initial fetch, then refresh every 2.5 seconds
fetchStatus();
setInterval(fetchStatus, 2500);
