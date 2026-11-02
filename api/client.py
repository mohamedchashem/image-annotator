"""Command-line client for the gRPC annotation API.

Usage:
  python api/client.py submit <image> [--classes person,car] [--min-confidence 0.5]
  python api/client.py result <job_id>
  python api/client.py run <image> [--classes person,car] [--min-confidence 0.5]

Server address from GRPC_ADDRESS (default localhost:50051).
"run" and "result" save the annotated image into annotated/annotated_<job_id>.jpg.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import grpc

import annotator_pb2 as pb
import annotator_pb2_grpc as pb_grpc

ADDRESS = os.environ.get("GRPC_ADDRESS", "localhost:50051")
POLL_INTERVAL = 1.0  # seconds between polls
POLL_TIMEOUT = 60.0  # give up after a minute
OUTPUT_DIR = Path("annotated")  # result images land here, never in the repo root
# Must match api/server.py: GetResult returns a whole annotated JPEG, which is
# bigger than gRPC's 4 MB default message cap on large photos.
MAX_MESSAGE_BYTES = 32 * 1024 * 1024  # 32 MB gRPC message limit
GRPC_OPTIONS = (
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
)


def submit(stub, image_path, classes, min_confidence):
    """Upload the image and return the job id the server assigned."""
    request = pb.SubmitImageRequest(image=Path(image_path).read_bytes())
    if classes:
        request.classes.extend(classes)
    if min_confidence is not None:
        request.min_confidence = min_confidence
    return stub.SubmitImage(request, timeout=30).job_id


def print_result(response, job_id):
    """Print one result and save the annotated image when the job is DONE."""
    print(f"status: {pb.GetResultResponse.Status.Name(response.status)}")
    for d in response.detections:
        print(f"  {d.label} {d.confidence:.2f} box=({d.x1}, {d.y1}, {d.x2}, {d.y2})")
    if response.error:
        print(f"error: {response.error}")
    if response.status == pb.GetResultResponse.DONE:
        out = OUTPUT_DIR / f"annotated_{job_id}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)  # first run: no folder yet
        out.write_bytes(response.annotated_image)
        print(f"saved {out}")


def run(stub, image_path, classes, min_confidence):
    """Submit, then poll until the job is done or failed (60 s timeout)."""
    job_id = submit(stub, image_path, classes, min_confidence)
    print(f"job_id: {job_id}")

    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        response = stub.GetResult(pb.GetResultRequest(job_id=job_id), timeout=30)
        if response.status != pb.GetResultResponse.PENDING:
            return print_result(response, job_id)
        time.sleep(POLL_INTERVAL)
    print(f"gave up after {POLL_TIMEOUT:.0f}s, job {job_id} is still pending")


def main():
    parser = argparse.ArgumentParser(description="gRPC client for the annotator")
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("submit", "run"):
        cmd = commands.add_parser(name)
        cmd.add_argument("image", help="path to the image file")
        cmd.add_argument("--classes", default="", help="comma separated labels")
        cmd.add_argument("--min-confidence", type=float, default=None)

    cmd = commands.add_parser("result")
    cmd.add_argument("job_id")

    args = parser.parse_args()

    channel = grpc.insecure_channel(ADDRESS, options=GRPC_OPTIONS)
    stub = pb_grpc.ImageAnnotatorStub(channel)
    try:
        if args.command == "result":
            response = stub.GetResult(pb.GetResultRequest(job_id=args.job_id), timeout=30)
            print_result(response, args.job_id)
        else:
            classes = [c.strip() for c in args.classes.split(",") if c.strip()]
            if args.command == "submit":
                print(submit(stub, args.image, classes, args.min_confidence))
            else:
                run(stub, args.image, classes, args.min_confidence)
    except grpc.RpcError as exc:
        # Server-side errors: INVALID_ARGUMENT, NOT_FOUND, UNAVAILABLE, ...
        print(f"RPC failed: {exc.code().name}: {exc.details()}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


if __name__ == "__main__":
    main()
