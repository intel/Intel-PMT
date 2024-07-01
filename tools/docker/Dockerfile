FROM python:3-slim@sha256:da2d7af143dab7cd5b0d5a5c9545fe14e67fc24c394fcf1cf15e8ea16cbd8637

WORKDIR /usr/src/app

COPY tools/docker/requirements.txt ./

RUN apt-get update && apt-get install -y --no-install-recommends g++=4:12.2.0-3 gcc=4:12.2.0-3 libxslt1-dev=1.1.35-1 netcat-traditional=1.10-47 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get remove -y g++ gcc libxslt1-dev && apt-get autoremove -y && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

COPY xml ./xml
COPY tools/docker/config ./config
COPY tools/collectd-agent/pmt.py ./pmt.py
COPY tools/docker/entrypoint.sh ./entrypoint.sh
COPY tools/docker/otelcol-contrib ./otelcol-contrib

EXPOSE 9100/tcp

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]