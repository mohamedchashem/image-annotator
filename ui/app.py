"""FastAPI web UI for the image-annotation pipeline.

The browser only ever talks to this process, which is a plain gRPC client of
api/server.py:

    browser --HTTP--> ui/app.py --gRPC--> api/server.py --AMQP--> worker

The generated stubs in api/ are imported as-is (never edited), so the only
files this app needs from api/ are annotator_pb2.py and annotator_pb2_grpc.py.

Routes
    GET  /                        the page (ui/static/index.html)
    POST /api/annotate            multipart "image" -> {"job_id": "..."}
    GET  /api/jobs/{job_id}       -> {"status": "PENDING|DONE|FAILED", "error": ""}
    GET  /api/jobs/{job_id}/image annotated JPEG; "?download=1" saves it

Config via environment variables:
  GRPC_ADDRESS   default: localhost:50051

Run with: uvicorn ui.app:app --host 0.0.0.0 --port 8000 --no-access-log
"""

import logging
import os
import sys
import time
from pathlib import Path

import grpc
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

UI_DIR = Path(__file__).resolve().parent
API_DIR = UI_DIR.parent / "api"     # the generated stubs, next to the project root
STATIC_DIR = UI_DIR / "static"
sys.path.insert(0, str(API_DIR))    # makes "import annotator_pb2" resolve here

import annotator_pb2 as pb            # noqa: E402  (sys.path setup has to come first)
import annotator_pb2_grpc as pb_grpc  # noqa: E402

GRPC_ADDRESS = os.environ.get("GRPC_ADDRESS", "localhost:50051")
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # same limit the API enforces
CHUNK_BYTES = 64 * 1024
SUBMIT_TIMEOUT = 30.0               # seconds: a submit only stores + queues
RESULT_TIMEOUT = 15.0
# Must match api/server.py: a finished job sends back the whole annotated JPEG,
# which is larger than gRPC's 4 MB default cap on big photos.
MAX_MESSAGE_BYTES = 32 * 1024 * 1024  # 32 MB gRPC message limit
GRPC_OPTIONS = (
    ("grpc.max_send_message_length", MAX_MESSAGE_BYTES),
    ("grpc.max_receive_message_length", MAX_MESSAGE_BYTES),
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ui")

app = FastAPI(title="Image Annotator UI", docs_url=None, redoc_url=None, openapi_url=None)

# One channel for the whole process: gRPC channels are thread-safe and
# reconnect on their own, so there is nothing to manage per request.
_channel = grpc.insecure_channel(GRPC_ADDRESS, options=GRPC_OPTIONS)
_stub = pb_grpc.ImageAnnotatorStub(_channel)


def grpc_http_error(exc):
    """Translate a gRPC failure into an HTTPException with plain-English text."""
    code = exc.code()
    detail = (exc.details() or "").strip()
    if code is grpc.StatusCode.INVALID_ARGUMENT:
        message = f"Invalid request: {detail}." if detail else "The request was invalid."
        return HTTPException(status_code=400, detail=message)
    if code is grpc.StatusCode.NOT_FOUND:
        return HTTPException(status_code=404, detail="No job with that id was found.")
    if code is grpc.StatusCode.RESOURCE_EXHAUSTED:
        # The annotated image alone is bigger than the gRPC message cap.
        return HTTPException(
            status_code=413,
            detail=(
                "The annotated image is too large to send back "
                f"(over {MAX_MESSAGE_BYTES // (1024 * 1024)} MB). "
                "Please try a smaller image."
            ),
        )
    if code is grpc.StatusCode.UNAVAILABLE:
        return HTTPException(
            status_code=503,
            detail="The annotation service is unavailable right now. Please try again.",
        )
    return HTTPException(
        status_code=502,
        detail="The annotation service returned an unexpected error.",
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Every error leaves this app as {"error": "..."}, whatever raised it."""
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """A malformed request (e.g. no "image" field) is a 400 in the same shape."""
    fields = [str(part) for error in exc.errors() for part in error.get("loc", ())]
    if "image" in fields:
        message = 'Send the image as multipart/form-data in a field named "image".'
    else:
        message = "The request was invalid."
    return JSONResponse(status_code=400, content={"error": message})


@app.middleware("http")
async def log_one_line_per_request(request: Request, call_next):
    """Exactly one log line per request (uvicorn's access log is switched off)."""
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - started) * 1000
        log.exception("%s %s -> 500 in %.0f ms", request.method, request.url.path, elapsed)
        raise
    elapsed = (time.perf_counter() - started) * 1000
    log.info(
        "%s %s -> %d in %.0f ms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


def get_result(job_id: str):
    """GetResult over gRPC, with gRPC failures mapped onto HTTP exceptions."""
    try:
        return _stub.GetResult(pb.GetResultRequest(job_id=job_id), timeout=RESULT_TIMEOUT)
    except grpc.RpcError as exc:
        raise grpc_http_error(exc) from exc


def read_upload(image: UploadFile) -> bytes:
    """Read the upload in chunks and refuse anything over MAX_IMAGE_BYTES."""
    data = bytearray()
    while True:
        chunk = image.file.read(CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:  # stop reading, before gRPC is called
            raise HTTPException(
                status_code=413,
                detail="That image is larger than 10 MB. Please choose a smaller file.",
            )
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file was empty.")
    return bytes(data)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """The page itself: one self-contained HTML file, no build step."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/annotate")
def annotate(image: UploadFile = File(...)) -> dict:
    """Store the upload through the API and hand the job id back to the page."""
    try:
        data = read_upload(image)   # 400/413 here, before any gRPC call
    finally:
        image.file.close()
    try:
        submitted = _stub.SubmitImage(pb.SubmitImageRequest(image=data), timeout=SUBMIT_TIMEOUT)
    except grpc.RpcError as exc:
        raise grpc_http_error(exc) from exc
    return {"job_id": submitted.job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    """Poll target for the page: status + error text only, never image bytes."""
    result = get_result(job_id)
    return {
        "status": pb.GetResultResponse.Status.Name(result.status),
        "error": result.error or "",
    }


@app.get("/api/jobs/{job_id}/image")
def job_image(job_id: str, download: bool = False) -> Response:
    """The annotated JPEG, inline by default and as an attachment when asked."""
    result = get_result(job_id)
    status = pb.GetResultResponse.Status.Name(result.status)
    if status == "PENDING":
        raise HTTPException(status_code=409, detail="That job is still running.")
    if status == "FAILED":
        reason = result.error or "unknown error"
        raise HTTPException(status_code=409, detail=f"That job failed: {reason}")
    if not result.annotated_image:
        raise HTTPException(
            status_code=502,
            detail="The annotation service returned an empty image.",
        )
    headers = {}
    if download:
        # Safe to interpolate: the API already rejected any non-UUID job_id.
        headers["Content-Disposition"] = f'attachment; filename="annotated_{job_id}.jpg"'
    return Response(content=result.annotated_image, media_type="image/jpeg", headers=headers)
