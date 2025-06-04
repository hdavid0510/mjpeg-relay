FROM python:3.13-slim AS builder

RUN	apt-get update -qq \
	&& apt-get install -qy build-essential gcc libffi-dev python3-dev

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip wheel \
	&& pip wheel --no-cache-dir -r requirements.txt -w /build/wheels


FROM python:3.13-slim AS runtime

COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --find-links=/wheels uvloop aiohttp \
	&& find /usr/local -name '*.so' -exec strip --strip-unneeded {} + || true \
	&& pip uninstall -y pip setuptools wheel || true

WORKDIR /app
COPY . .

EXPOSE 54321 54322
ENTRYPOINT ["python", "relay.py"]
CMD []
