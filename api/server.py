"""gRPC front door for the image-annotation pipeline.

The stubs are generated from api/annotator.proto. After editing the proto, run
this from the project root (the generated *_pb2*.py files live in api/):

    .venv/bin/python -m grpc_tools.protoc -I api --python_out=api \
        --pyi_out=api --grpc_python_out=api api/annotator.proto

Run with: python api/server.py   (the script's own folder is on sys.path, so the
generated "import annotator_pb2" resolves.)

Config via environment variables:
  GRPC_PORT      default: 50051
  RABBITMQ_HOST  default: localhost
  DATA_DIR       default: ./data
"""

import io
import json
import os
import signal
import threading
import uuid
from concurrent import futures
from pathlib import Path

import grpc
import pika
from PIL import Image

import annotator_pb2 as pb
import annotator_pb2_grpc as pb_grpc

QUEUE = "image_jobs"
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB upload limit
# gRPC caps messages at 4 MB by default, which is smaller than a full-size
# annotated photo (the result carries the whole JPEG plus the detections), so
# both directions are raised to 32 MB. MAX_IMAGE_BYTES still limits uploads.
MAX_MESSAGE_BYTES = 32 * 1024 * 1024  # 32 MB gRPC message limit
GRPC_OPTIONS = (
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
)
GRPC_PORT = os.environ.get("GRPC_PORT", "50051")
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
INPUTS = DATA_DIR / "inputs"
RESULTS = DATA_DIR / "results"


def publish_job(message):
    """Publish one persistent job message to the durable 'image_jobs' queue."""
    # A fresh connection per request on purpose: pika's BlockingConnection is
    # not thread-safe, and gRPC serves calls from several pool threads at once.
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    try:
        channel = connection.channel()
        # Declare the queue the worker consumes from (must match: durable).
        channel.queue_declare(queue=QUEUE, durable=True)
        channel.basic_publish(
            exchange="",  # default exchange -> routed by queue name
            routing_key=QUEUE,
            body=json.dumps(message),
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
    finally:
        connection.close()


class ImageAnnotator(pb_grpc.ImageAnnotatorServicer):
    """gRPC service implementation (a class only because gRPC requires one)."""

    def SubmitImage(self, request, context):
        # 1. Validate the upload: present, small enough, and really an image.
        if not request.image:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "image is empty")
        if len(request.image) > MAX_IMAGE_BYTES:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "image is larger than 10 MB")
        try:
            with Image.open(io.BytesIO(request.image)) as img:
                img.verify()  # raises if the bytes are not a real image
        except Exception:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "not a valid image")

        # 2. The job id is always ours: a client cannot choose or overwrite one.
        job_id = str(uuid.uuid4())

        # 3. Store it where the worker looks for it: inputs/<job_id>.jpg (JPEG).
        INPUTS.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(request.image)) as img:
            img.convert("RGB").save(INPUTS / f"{job_id}.jpg", "JPEG")

        # 4. Queue the job; leave out the options the client did not send.
        message = {"job_id": job_id}
        if request.HasField("min_confidence"):
            message["min_confidence"] = request.min_confidence
        if request.classes:
            message["classes"] = list(request.classes)
        try:
            publish_job(message)
        except (pika.exceptions.AMQPError, OSError) as exc:
            # Not queued -> drop the stored image, or GetResult would report a
            # "PENDING" job that no worker will ever pick up.
            (INPUTS / f"{job_id}.jpg").unlink(missing_ok=True)
            reason = str(exc) or type(exc).__name__  # pika errors can be empty
            context.abort(
                grpc.StatusCode.UNAVAILABLE,
                f"cannot queue job: RabbitMQ at {RABBITMQ_HOST} is unreachable ({reason})",
            )

        print(f"[SubmitImage] {job_id} queued {message}", flush=True)
        return pb.SubmitImageResponse(job_id=job_id)

    def GetResult(self, request, context):
        # 1. Only accept the kind of id we hand out (blocks path traversal too).
        try:
            job_id = str(uuid.UUID(request.job_id))
        except ValueError:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_id must be a UUID")

        # 2. No result file yet: either still queued/processing or unknown job.
        result_file = RESULTS / f"{job_id}.json"
        if not result_file.is_file():
            if (INPUTS / f"{job_id}.jpg").is_file():
                print(f"[GetResult] {job_id} PENDING", flush=True)
                return pb.GetResultResponse(status=pb.GetResultResponse.PENDING)
            context.abort(grpc.StatusCode.NOT_FOUND, f"unknown job_id {job_id}")

        # 3. Result exists: map the worker's JSON onto the protobuf response.
        data = json.loads(result_file.read_text())
        if data["status"] == "done":
            detections = [
                pb.Detection(
                    label=d["label"],
                    confidence=d["confidence"],
                    x1=d["box"][0],
                    y1=d["box"][1],
                    x2=d["box"][2],
                    y2=d["box"][3],
                )
                for d in data["detections"]
            ]
            print(f"[GetResult] {job_id} DONE ({len(detections)} detections)", flush=True)
            return pb.GetResultResponse(
                status=pb.GetResultResponse.DONE,
                detections=detections,
                annotated_image=(RESULTS / f"{job_id}.jpg").read_bytes(),
            )

        print(f"[GetResult] {job_id} FAILED", flush=True)
        return pb.GetResultResponse(
            status=pb.GetResultResponse.FAILED,
            error=data.get("error") or "",
        )


def serve():
    INPUTS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    # Thread pool: one process serving several clients concurrently.
    # GRPC_OPTIONS raises the 4 MB message cap so big result images fit.
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8), options=GRPC_OPTIONS)
    pb_grpc.add_ImageAnnotatorServicer_to_server(ImageAnnotator(), server)
    if server.add_insecure_port(f"[::]:{GRPC_PORT}") == 0:
        raise SystemExit(f"cannot bind port {GRPC_PORT}")
    server.start()
    print(
        f"server ready: port={GRPC_PORT} rabbitmq={RABBITMQ_HOST} data_dir={DATA_DIR}",
        flush=True,
    )

    # Block until SIGINT (Ctrl+C) or SIGTERM, then stop serving gracefully.
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    stop.wait()
    server.stop(grace=5).wait()
    print("server stopped", flush=True)


if __name__ == "__main__":
    serve()
