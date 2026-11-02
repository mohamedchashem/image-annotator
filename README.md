# image-annotator

Upload an image and get it back with the detected objects drawn on it: a worker
runs YOLOv8n on the image and stores the result on a shared volume that the API
serves back. It is a learning project for practising gRPC, RabbitMQ, Docker,
Docker Compose, Kubernetes and Linux, not a product.

## How it works

```
Browser --HTTP--> ui (FastAPI, :8000) --gRPC--> api (:50051)
                                                   | publish
                                                   v
                                      RabbitMQ queue "image_jobs"
                                                   | consume
                                                   v
                                        worker (YOLOv8n, CPU) --> writes
                                                   |
    shared volume /data: inputs/<job_id>.jpg, results/<job_id>.jpg + .json
```

1. The browser sends the image to the ui, which forwards it to the api over gRPC.
2. The api checks the upload, writes /data/inputs/<job_id>.jpg, publishes a JSON
   message to the queue and returns the job id at once.
3. The worker handles one message at a time and writes
   /data/results/<job_id>.json and /data/results/<job_id>.jpg.
4. The ui polls the api, which reads that JSON and reports PENDING, DONE or
   FAILED; a finished job also returns the annotated JPEG. If a service
   restarts, the job simply stays queued until a worker acks it.

## Project structure

```
annotate.py          run the detector on one image from the command line
compose.yaml         the four services: rabbitmq, api, worker, ui
requirements-*.txt   pinned dependencies for the api and worker images
samples/             input test images (bus.jpg)
annotated/           output of annotate.py and api/client.py, not committed
api/                 proto, generated stubs, gRPC server, CLI client
worker/              worker.py (queue consumer) and detector.py (YOLOv8n)
ui/                  FastAPI app and one static HTML page
k8s/                 kind manifests: namespace, broker, PVC, api, worker
rabbit_demo/         two small scripts used to learn RabbitMQ
docs/DEMO.md         walkthrough for presenting the project
```

## Requirements

- Docker with Compose. For Kubernetes: kind and kubectl. Developed on WSL2 Ubuntu.
- Python 3.12 in a virtualenv, only to run annotate.py or api/client.py.

## Run with Docker Compose

```
docker compose up -d --build      # then open http://localhost:8000
docker compose ps
docker compose logs -f worker     # one line per job
docker compose down               # stops the containers, volumes stay
```

The broker management page is published on http://localhost:15672 (guest/guest).

## Run on Kubernetes (kind)

The manifests expect a local kind cluster with both images loaded into the node.

```
kind create cluster --name image-annotator
docker build -t image-annotator-api:v1 -f api/Dockerfile .
docker build -t image-annotator-worker:v1 -f worker/Dockerfile .
kind load docker-image image-annotator-api:v1 --name image-annotator
kind load docker-image image-annotator-worker:v1 --name image-annotator
kubectl apply -f k8s/                                        # 00-namespace .. 40-worker
kubectl get pods -n image-annotator                          # wait for Running
kubectl scale deployment worker --replicas=2 -n image-annotator
kubectl port-forward -n image-annotator svc/api 50051:50051  # api for a host client
kind delete cluster --name image-annotator
```

The web UI is not in the Kubernetes manifests; use the port-forward for the api.

## Command line tools

```
python annotate.py samples/bus.jpg            # writes annotated/bus_annotated.jpg
python api/client.py submit samples/bus.jpg   # prints a job id
python api/client.py result <job_id>          # writes annotated/annotated_<job_id>.jpg
```

The client talks to localhost:50051, so the api container or port-forward must be
running. GRPC_ADDRESS overrides that address.

## Design notes

- The queue lets the api answer as soon as the file is stored and the job is
  queued, while the slow model works in the background.
- The worker acks only after the result file is written, so a job that dies
  halfway is redelivered by the broker when the worker comes back.
- Results are written via a temp file and rename, so no partial JSON is ever read.
- The model is loaded once when the worker starts (worker/detector.py), not per job.
- The gRPC limit was raised from 4 MB to 32 MB in api/server.py, api/client.py
  and ui/app.py: one large photo gave a result of about 4.2 MB and the client
  failed with RESOURCE_EXHAUSTED.
- Containers run as a non-root user (uid 10001); in the cluster an initContainer
  fixes the ownership of the hostPath-backed volume first.

## Known limitations

- Only a single node kind cluster with one ReadWriteOnce volume was tried.
- No authentication, no TLS, and RabbitMQ still uses guest/guest.
- Results are never cleaned up, so /data or the PVC grows until deleted by hand.
- CPU only, roughly one to two seconds per image.
- Only the general YOLOv8n model with its 80 COCO classes.
- No database: job state is a file in /data, so history goes with the volume.

## License

The code has no license yet, so all rights stay reserved by default. The model is
YOLOv8n from Ultralytics and is licensed under AGPL-3.0; check that license
before using this project anywhere public.
