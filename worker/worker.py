"""RabbitMQ worker: annotate image jobs from the durable 'image_jobs' queue.

Config via environment variables:
  RABBITMQ_HOST  default: localhost
  DATA_DIR       default: ./data
"""

import json
import os
import signal
import threading
import time
from pathlib import Path

import pika

from detector import annotate  # same folder: the worker is run as a script

QUEUE = "image_jobs"
HOST = os.environ.get("RABBITMQ_HOST", "localhost")
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
INPUTS = DATA_DIR / "inputs"
RESULTS = DATA_DIR / "results"

RETRY_DELAY = 2.0   # seconds between broker connection attempts
POLL_TIMEOUT = 0.2  # seconds spent waiting for a message before re-checking 'stop'

# Set by the SIGTERM / SIGINT handlers; the loops in main() poll it so that
# shutdown always happens between jobs (the current job still gets acked).
stop = threading.Event()


def write_result_atomic(job_id, payload):
    """Write <job_id>.json atomically: temp file in the same folder, then rename."""
    tmp = RESULTS / f".{job_id}.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, RESULTS / f"{job_id}.json")  # rename is atomic


def handle(channel, method, properties, body):
    """Handle one job: annotate the image, write the result JSON, then ack."""
    started = time.time()
    job_id = "unknown"

    # 1. Parse the message. A broken message must not crash the worker.
    try:
        job = json.loads(body)
        job_id = str(job.get("job_id") or "unknown")
        if job_id == "unknown":
            raise ValueError("message has no job_id")

        # 2. Run the detector on DATA_DIR/inputs/<job_id>.jpg.
        image_in = INPUTS / f"{job_id}.jpg"
        if not image_in.is_file():
            raise FileNotFoundError(f"input image not found: {image_in}")
        detections = annotate(
            image_in,
            RESULTS / f"{job_id}.jpg",
            min_confidence=float(job.get("min_confidence", 0.25)),
            classes=job.get("classes"),
        )
        result = {
            "job_id": job_id,
            "status": "done",
            "detections": detections,
            "annotated_image": f"{job_id}.jpg",
            "error": None,
        }
    except Exception as exc:
        # Any failure becomes a "failed" result instead of an endless retry.
        result = {
            "job_id": job_id,
            "status": "failed",
            "detections": [],
            "annotated_image": None,
            "error": f"{type(exc).__name__}: {exc}"[:200],
        }

    # 3. Write the JSON atomically, then ack: files are on disk before the ack.
    write_result_atomic(job_id, result)
    channel.basic_ack(delivery_tag=method.delivery_tag)

    # One log line per job: what arrived, the outcome, and how long it took.
    took = time.time() - started
    line = f"[{job_id}] received -> {result['status']} in {took:.2f}s"
    if result["error"]:
        line += f" ({result['error']})"
    print(line, flush=True)


def connect():
    """Connect to the broker (guest/guest) and declare the same durable queue.

    Keeps retrying every RETRY_DELAY seconds, forever, until it works or a stop
    is requested. Returns (None, None) if we were told to stop while retrying.
    """
    while not stop.is_set():
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=HOST))
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE, durable=True)  # 4. same durable queue
            # 5. Prefetch 1: one unacked job at a time, so work spreads over workers.
            channel.basic_qos(prefetch_count=1)
            return connection, channel
        except (pika.exceptions.AMQPError, OSError) as exc:
            reason = str(exc) or type(exc).__name__  # pika errors can be empty
            print(
                f"broker unreachable at {HOST} ({reason}), "
                f"retrying in {RETRY_DELAY:.0f}s",
                flush=True,
            )
            stop.wait(RETRY_DELAY)  # a signal ends this wait early
    return None, None


def close(connection):
    """Close a connection, ignoring errors on an already dead one."""
    try:
        connection.close()
    except Exception:
        pass


def main():
    # Ctrl+C / SIGTERM: just raise the flag; the job in flight still finishes.
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    # Make sure the folder layout exists before we start taking jobs.
    INPUTS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    while not stop.is_set():
        connection, channel = connect()
        if connection is None:  # stopped while waiting for the broker
            break

        # 6. Consume with manual acks (auto_ack=False); handle() acks when done.
        channel.basic_consume(queue=QUEUE, on_message_callback=handle, auto_ack=False)
        print(f"worker ready: host={HOST} data_dir={DATA_DIR} queue={QUEUE}", flush=True)

        try:
            # Pump the connection ourselves instead of channel.start_consuming():
            # start_consuming() blocks forever, while this wakes up every
            # POLL_TIMEOUT seconds so a signal is noticed within ~0.2s.
            while not stop.is_set():
                connection.process_data_events(time_limit=POLL_TIMEOUT)
        except (pika.exceptions.AMQPError, OSError) as exc:
            # Connection lost: any unacked job is requeued by the broker itself,
            # so it is redelivered (at-least-once) after we reconnect.
            reason = str(exc) or type(exc).__name__
            print(
                f"connection lost ({reason}), "
                f"reconnecting in {RETRY_DELAY:.0f}s",
                flush=True,
            )
        finally:
            close(connection)

    print("worker stopped", flush=True)
    # Returning from main() exits with status 0.


if __name__ == "__main__":
    main()
