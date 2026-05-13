#!/usr/bin/env python3

from influxdb_client import InfluxDBClient
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from urllib.parse import parse_qs


# ---------------- Data Fetch ----------------
def fetch_latency(target, registry):
    url = f"http://{target}"
    client = InfluxDBClient(url=url, timeout=5000)
    query_api = client.query_api()

    disk_read_latency_ms = Gauge(
        "ecs_disk_read_latency_ms",
        "Average disk read latency in milliseconds",
        ["node", "disk", "influx_addr", "disk_type"],
        registry=registry,
    )

    disk_write_latency_ms = Gauge(
        "ecs_disk_write_latency_ms",
        "Average disk write latency in milliseconds",
        ["node", "disk", "influx_addr", "disk_type"],
        registry=registry,
    )


    latency_query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -5m)
      |> filter(fn: (r) =>
          r["_measurement"] == "diskio" and
          (
              r["_field"] == "read_time" or
              r["_field"] == "reads" or
              r["_field"] == "write_time" or
              r["_field"] == "writes"
          )
      )
      |> group(columns: ["host", "SCSI_IDENT_SERIAL", "name", "_field"])
      |> last()
    '''

    latency_results = {}

    for record in query_api.query_stream(latency_query):
        host = record.values["host"]

        # disk = record.values.get("name")
        # if not disk:
        #     disk = record.values.get("SCSI_IDENT_SERIAL", "unknown")
        disk = (
                record.values.get("name")
                or record.values.get("SCSI_IDENT_SERIAL")
                or "unknown"
        )

        field = record.get_field()
        value = record.get_value()

        if host not in latency_results:
            latency_results[host] = {}

        if disk not in latency_results[host]:
            latency_results[host][disk] = {}

        latency_results[host][disk][field] = value

    # calculate latencies
    for host, disks in latency_results.items():
        #print(host)
        for disk, values in disks.items():

            #print(f'{disk}: {",".join(values)}')
            disk_type = "logical" if disk.startswith("ECS/") else "physical"
            reads = values.get("reads", 0)
            read_time = values.get("read_time", 0)

            writes = values.get("writes", 0)
            write_time = values.get("write_time", 0)

            read_latency = 0
            write_latency = 0

            if reads > 0:
                read_latency = read_time / reads

            if writes > 0:
                write_latency = write_time / writes

            disk_read_latency_ms.labels(
                node=host,
                disk=disk,
                influx_addr=target,
                disk_type=disk_type,
            ).set(read_latency)

            disk_write_latency_ms.labels(
                node=host,
                disk=disk,
                influx_addr=target,
                disk_type=disk_type,
            ).set(write_latency)

    client.close()


def fetch_disk(target, registry):
    url = f"http://{target}"
    client = InfluxDBClient(url=url, timeout=5000)
    query_api = client.query_api()

    ecs_disk_inodes_used = Gauge(
        "ecs_disk_inodes_used",
        "ECS node disk used inodes",
        ["node", "path", "influx_addr"],
        registry=registry,
    )

    ecs_disk_inodes_free = Gauge(
        "ecs_disk_inodes_free",
        "ECS node disk free inodes",
        ["node", "path", "influx_addr"],
        registry=registry,
    )

    ecs_disk_inodes_total = Gauge(
        "ecs_disk_inodes_total",
        "ECS node disk total inodes",
        ["node", "path", "influx_addr"],
        registry=registry,
    )

    ecs_disk_usage_bytes = Gauge(
        "ecs_disk_usage_bytes",
        "ECS node disk usage in bytes",
        ["node", "path", "influx_addr"],
        registry=registry,
    )

    ecs_disk_free_bytes = Gauge(
        "ecs_disk_free_bytes",
        "ECS node disk usage in bytes",
        ["node", "path", "influx_addr"],
        registry=registry,
    )

    ecs_disk_total_bytes = Gauge(
        "ecs_disk_total_bytes",
        "ECS node disk total in bytes",
        ["node", "path", "influx_addr"],
        registry=registry,
    )

    ecs_disk_usage_percent = Gauge(
        "ecs_disk_usage_percent",
        "ECS node disk usage in percents",
        ["node", "path", "influx_addr"],
        registry=registry,
    )


    disk_query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -5m)
      |> filter(fn: (r) =>
          r["_measurement"] == "disk"
      )
      |> group(columns: ["host", "path", "_field"])
      |> last()
    '''

    disk_results = {}

    for record in query_api.query_stream(disk_query):
        host = record.values["host"]
        path = record.values.get("path", "unknown")
        field = record.get_field()
        value = record.get_value()

        if host not in disk_results:
            disk_results[host] = {}

        if path not in disk_results[host]:
            disk_results[host][path] = {}

        disk_results[host][path][field] = value

    for host, path in disk_results.items():
        for path, m in path.items():

            disk_used = m.get("used", 0)
            disk_free = m.get("free", 0)
            disk_total = m.get("total")
            disk_used_percent = m.get("used_percent")

            inodes_used = m.get("inodes_used", 0)
            inodes_free = m.get("inodes_free", 0)
            inodes_total = m.get("inodes_total", 0)

            if disk_total is None:
                disk_total = disk_used + disk_free

            if disk_used_percent is None and disk_total > 0:
                disk_used_percent = (disk_used / disk_total) * 100

            ecs_disk_usage_bytes.labels(node=host, influx_addr=target, path=path).set(disk_used)
            ecs_disk_free_bytes.labels(node=host, influx_addr=target, path=path).set(disk_free)
            ecs_disk_total_bytes.labels(node=host, influx_addr=target, path=path).set(disk_total)
            ecs_disk_usage_percent.labels(node=host, influx_addr=target, path=path).set(disk_used_percent)

            ecs_disk_inodes_used.labels(node=host, influx_addr=target, path=path).set(inodes_used)
            ecs_disk_inodes_free.labels(node=host, influx_addr=target, path=path).set(inodes_free)
            ecs_disk_inodes_total.labels(node=host, influx_addr=target, path=path).set(inodes_total)

    client.close()

def fetch_cpu(target, registry):
    url = f"http://{target}"
    client = InfluxDBClient(url=url, timeout=5000)
    query_api = client.query_api()

    ecs_cpu_usage_iowait = Gauge(
        "ecs_cpu_usage_iowait",
        "ECS node cpu usage iowait",
        ["node", "influx_addr"],
        registry=registry,
    )

    ecs_cpu_usage_user = Gauge(
        "ecs_cpu_usage_user",
        "ECS node cpu usage by user apps",
        ["node", "influx_addr"],
        registry=registry,
    )

    ecs_cpu_usage_system = Gauge(
        "ecs_cpu_usage_system",
        "ECS node cpu usage by system apps",
        ["node", "influx_addr"],
        registry=registry,
    )

    ecs_cpu_usage_percent = Gauge(
        "ecs_cpu_usage_percent",
        "ECS node cpu usage percentage",
        ["node", "influx_addr"],
        registry=registry,
        )

    cpu_results = {}

    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -5m)
      |> filter(fn: (r) =>
          r["_measurement"] == "cpu" and
          r["cpu"] == "cpu-total" and
          (
            r["_field"] == "usage_idle" or
            r["_field"] == "usage_system" or
            r["_field"] == "usage_user" or
            r["_field"] == "usage_iowait"
          )
      )
      |> group(columns: ["host", "_field"])
      |> last()
    '''

    for record in query_api.query_stream(query):
        host = record.values["host"]
        field = record.get_field()
        value = record.get_value()
        #print(f"{host}\t{field}\t{value}")

        if host not in cpu_results:
            cpu_results[host] = {}

        cpu_results[host][field] = value

    # Populate metrics
    for host, m in cpu_results.items():
        idle = m.get("usage_idle", 0)
        system = m.get("usage_system", 0)
        user = m.get("usage_user", 0)
        iowait = m.get("usage_iowait", 0)
        usage = 100 - idle

        ecs_cpu_usage_system.labels(node=host, influx_addr=target).set(system)
        ecs_cpu_usage_user.labels(node=host, influx_addr=target).set(user)
        ecs_cpu_usage_iowait.labels(node=host, influx_addr=target).set(iowait)
        ecs_cpu_usage_percent.labels(node=host, influx_addr=target).set(usage)

    client.close()

def fetch_memory(target, registry):
    url = f"http://{target}"
    client = InfluxDBClient(url=url, timeout=5000)
    query_api = client.query_api()

    ecs_memory_total = Gauge(
        "ecs_memory_total_bytes",
        "ECS node total memory",
        ["node", "influx_addr"],
        registry=registry,
    )

    ecs_memory_used = Gauge(
        "ecs_memory_used_bytes",
        "ECS node used memory",
        ["node", "influx_addr"],
        registry=registry,
    )

    ecs_memory_free = Gauge(
        "ecs_memory_free_bytes",
        "ECS node free memory",
        ["node", "influx_addr"],
        registry=registry,
    )

    memory_results = {}

    query = f'''
    from(bucket: "{BUCKET}")
      |> range(start: -5m)
      |> filter(fn: (r) =>
          r["_measurement"] == "mem" and
          (r["_field"] == "free" or
           r["_field"] == "used" or
           r["_field"] == "total")
      )
      |> group(columns: ["host", "_field"])
      |> last()
    '''

    for record in query_api.query_stream(query):
        host = record.values["host"]
        field = record.get_field()
        value = record.get_value()

        if host not in memory_results:
            memory_results[host] = {}

        memory_results[host][field] = value

    # Populate metrics
    for host, m in memory_results.items():
        free = m.get("free", 0)
        used = m.get("used", 0)
        total = m.get("total")

        if total is None:
            total = free + used

        ecs_memory_free.labels(node=host, influx_addr=target).set(free)
        ecs_memory_used.labels(node=host, influx_addr=target).set(used)
        ecs_memory_total.labels(node=host, influx_addr=target).set(total)

    client.close()


# ---------------- Config ----------------
BUCKET = "monitoring_op"

# ---------------- WSGI App ----------------
def app(environ, start_response):
    path = environ.get("PATH_INFO", "")

    # Health endpoint
    if path == "/health":
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"OK"]

    if path != "/metrics":
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"Not Found"]

    params = parse_qs(environ.get("QUERY_STRING", ""))
    target = params.get("target", [None])[0]

    if not target:
        start_response("400 Bad Request", [("Content-Type", "text/plain")])
        return [b"Missing target parameter"]

    # new registry per request
    registry = CollectorRegistry()

    try:
        fetch_memory(target, registry)
        fetch_disk(target, registry)
        fetch_cpu(target, registry)
        fetch_latency(target, registry)

    except Exception as e:
        start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
        return [f"Error: {str(e)}".encode()]

    output = generate_latest(registry)

    start_response("200 OK", [("Content-Type", CONTENT_TYPE_LATEST)])
    return [output]

# gunicorn -w 2 --threads 2 --timeout 10 -b 0.0.0.0:9545 file_name:app