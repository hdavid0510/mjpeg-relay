FROM --platform=$TARGETPLATFORM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV SOURCE_URL="http://localhost:8081/?action=stream"

COPY . /
RUN	apt -qq  -o=Dpkg::Use-Pty=0 update  \
&&	apt -qqy -o=Dpkg::Use-Pty=0 upgrade \
&&	apt -qqy -o=Dpkg::Use-Pty=0 clean \
&&	rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
&&	pip3 install -r /requirements.txt \
&&	pip3 cache purge

EXPOSE 54321
EXPOSE 54322
CMD ["python", "/relay.py"]
