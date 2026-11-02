# Demo notes

A five-minute walkthrough, using the commands from the README.

1. `docker compose up -d --build`, then wait for four services in `docker compose ps`.
2. Warm up before the audience arrives: open http://localhost:8000 and annotate
   `samples/bus.jpg` once, so the model is already loaded.
3. Show the UI: annotate `samples/bus.jpg` again and point at the result next to
   the original.
4. Queue: `docker compose stop worker`, upload an image, show that the job stays
   PENDING, then `docker compose start worker` and let it finish on its own.
   `docker compose logs -f worker` prints one line per job.
5. Reconnect: `docker compose restart rabbitmq` and show the worker log report
   the lost connection, then the reconnect.
6. Pods: `kubectl get pods -n image-annotator`, then
   `kubectl delete pod -n image-annotator -l app=worker` and watch a new worker
   start with `kubectl get pods -n image-annotator -w`.
7. Clean up: `docker compose down` and `kind delete cluster --name image-annotator`.
