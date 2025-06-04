function pad(n) { return n < 10 ? "0" + n : n; }

function formatHMS(totalSeconds) {
	// Convert a raw number of seconds → "H:MM:SS"
	totalSeconds = Math.floor(totalSeconds);
	const hh = pad(Math.floor(totalSeconds / 3600));
	const mm = pad(Math.floor((totalSeconds % 3600) / 60));
	const ss = pad(totalSeconds % 60);
	return `${hh}:${mm}:${ss}`;
}

function formatTimestamp(epochSec) {
	// epochSec is in seconds → Date object
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
	// Convert bytes/sec to bits/sec → Mbps/Gbps
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
			// Uptime
			document.getElementById('uptime').textContent = formatHMS(data.uptime);

			// Inbound Bytes
			document.getElementById('received').textContent = humanBytes(data.received);

			// Inbound bps
			document.getElementById('bandwidth').textContent = humanBps(data.bandwidth);

			// Connected count
			document.getElementById('connection_count').textContent = data.connection_count;

			// Build table rows
			const tbody = document.getElementById('client_table_body');
			tbody.innerHTML = '';  // clear existing
			if (data.connection.length === 0) {
				const row = document.createElement('tr');
				const cell = document.createElement('td');
				cell.colSpan = 3;
				cell.textContent = 'No clients connected';
				row.appendChild(cell);
				tbody.appendChild(row);
			} else {
				data.connection.forEach(client => {
					const row = document.createElement('tr');
					const ipCell = document.createElement('td');
					ipCell.textContent = client.ip;
					const sinceCell = document.createElement('td');
					sinceCell.textContent = formatTimestamp(client.since);
					const outCell = document.createElement('td');
					outCell.textContent = humanBytes(client.sent);
					row.appendChild(ipCell);
					row.appendChild(sinceCell);
					row.appendChild(outCell);
					tbody.appendChild(row);
				});
			}

			// Last updated
			const now = new Date();
			document.getElementById('last_updated').textContent = now.toLocaleString();
		})
		.catch(err => {
			console.error('Error fetching /status:', err);
		});
}

// Initial fetch
fetchStatus();
// Refresh every 5 seconds
setInterval(fetchStatus, 5000);
