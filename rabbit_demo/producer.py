"""Publish 3 demo image jobs to RabbitMQ.

Usage: python rabbit_demo/producer.py
"""

import json
import uuid

import pika

QUEUE = "image_jobs"

# Connect to the broker (default guest/guest on localhost:5672).
connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
channel = connection.channel()

# Declare the queue as durable so it survives a broker restart.
# The consumer must declare it with the same options or its declare will fail.
channel.queue_declare(queue=QUEUE, durable=True)

# Publish 3 jobs; delivery_mode=2 makes each message persistent on disk.
for _ in range(3):
    job = {"job_id": str(uuid.uuid4()), "image_path": "bus.jpg"}
    channel.basic_publish(
        exchange="",  # the default exchange routes straight to a queue...
        routing_key=QUEUE,  # ...named by the routing key
        body=json.dumps(job),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    print(f"sent {json.dumps(job)}")

# Close the connection; this also flushes anything still buffered to the broker.
connection.close()
