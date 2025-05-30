FROM python:3.12-slim AS builder

RUN	apt-get update \
	&& apt-get install -y build-essential gcc libffi-dev python3-dev \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip wheel \
	&& pip wheel --no-cache-dir -r requirements.txt -w /build/wheels


FROM python:3.12-slim AS runtime

COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --find-links=/wheels uvloop aiohttp

WORKDIR /app
COPY . .

EXPOSE 54321 54322
ENTRYPOINT ["python", "relay.py"]
