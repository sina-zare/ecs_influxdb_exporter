FROM python:3.12-slim

WORKDIR /app

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --upgrade pip --index-url http://vnk-nexus.abramad.com/repository/pypi-proxy/simple --trusted-host vnk-nexus.abramad.com

RUN pip install --no-cache-dir -r requirements.txt --index-url http://vnk-nexus.abramad.com/repository/pypi-proxy/simple --trusted-host vnk-nexus.abramad.com
    
RUN useradd -r -s /usr/sbin/nologin exporter

COPY ecs_influxdb_exporter.py .

RUN chown -R exporter:exporter /app

USER exporter

EXPOSE 9545

CMD ["gunicorn", "-w", "2", "--threads", "4", "--timeout", "15", "-b", "0.0.0.0:9545", "ecs_influxdb_exporter:app"]