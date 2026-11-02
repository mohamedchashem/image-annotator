"""Consume demo image jobs from RabbitMQ. Press Ctrl+C to stop.

Usage: python rabbit_demo/consumer.py
"""

import json
import time

import pika

QUEUE = "image_jobs"


def handle(channel, method, properties, body):
    """Work on one message: print it, simulate work, then ack it manually."""
    job = json.loads(body)
    print(f"received {job}", flush=True)

    time.sleep(2)  # pretend to process the image

    # Manual ack: tells RabbitMQ the job is done and the message can be deleted.
    channel.basic_ack(delivery_tag=method.delivery_tag)
    print(f"acked {job['job_id']}", flush=True)


# Connect to the broker (default guest/guest on localhost:5672).
connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
channel = connection.channel()

# Declare the same durable queue, so the consumer can start before the producer.
channel.queue_declare(queue=QUEUE, durable=True)

# Prefetch 1: hand us only one unacked message at a time (fair dispatch).
channel.basic_qos(prefetch_count=1)

# Consume with auto_ack=False, i.e. nothing is acked until handle() says so.
channel.basic_consume(queue=QUEUE, on_message_callback=handle, auto_ack=False)

print(f"waiting for messages on '{QUEUE}' (Ctrl+C to stop)", flush=True)
try:
    channel.start_consuming()  # blocks, running handle() for each message
except KeyboardInterrupt:
    # Ctrl+C: stop consuming and close the connection cleanly.
    channel.stop_consuming()
    connection.close()
    print("stopped consuming", flush=True)
