# kbcicdlab — Kubernetes CI/CD Learning Lab

A hands-on lab that takes a small web app from source code to a running
Kubernetes deployment, and wires up a full CI/CD pipeline around it.

You will:

- **Containerize** a Python app with Docker (multi-layer alpine image, non-root user, `HEALTHCHECK`)
- **Deploy to Minikube** with raw manifests: Namespace, Deployment, Service, ConfigMap, Secret, liveness/readiness probes, resource limits
- **Package the same deployment as a Helm chart** and install/upgrade it with `helm`
- **Automate everything with GitHub Actions**: unit tests → build & push the image to GHCR → lint/render the Helm chart → spin up Minikube in CI, load the image, apply the manifests, and smoke-test the app

## Architecture

```
            git push (main)
                 │
                 ▼
        ┌─────────────────┐   build & push    ┌─────────┐
        │  GitHub Actions │ ─────────────────▶│  GHCR   │  ghcr.io/<owner>/kbcicdlab:<sha|latest>
        │   ci-cd.yaml    │                   └─────────┘
        └────────┬────────┘
                 │ apply k8s/ manifests + helm lint/template
                 ▼
        ┌─────────────────┐      NodePort :30080
        │  Minikube       │◀────────────────────────────┐
        │  namespace:     │   curl smoke test           │
        │  kbcicdlab      │─────────────────────────────┘
        │  ├─ Deployment (2 replicas, probes)
        │  ├─ Service (NodePort)
        │  ├─ ConfigMap
        │  └─ Secret
        └─────────────────┘
```

## Repository layout

```
├── app/                        # Sample app (Python 3 stdlib only, no pip deps)
│   ├── main.py                 #   HTTP server: /, /healthz, /readyz
│   └── test_main.py            #   unittest suite
├── Dockerfile                  # Container image definition
├── .dockerignore
├── k8s/                        # Raw Kubernetes manifests
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment.yaml         # probes, env from ConfigMap/Secret, resources
│   └── service.yaml            # NodePort 30080
├── helm/kbcicdlab/             # Helm chart for the same workload
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/              # _helpers.tpl, deployment, service, configmap, secret, NOTES.txt
├── .github/workflows/ci-cd.yaml # CI/CD pipeline
└── Makefile                    # Shortcuts for the commands below
```

## Prerequisites

- Docker
- Minikube (`minikube start --driver=docker`)
- kubectl
- Helm 3
- make (optional, for the shortcuts)
- GitHub CLI `gh` (optional, for working with the pipeline repo)

## Step 1 — Run the app locally

The app is a zero-dependency Python 3 HTTP server. Configuration comes from
environment variables (which Kubernetes will inject from a ConfigMap and a
Secret later):

| Endpoint   | Purpose                                  |
|------------|------------------------------------------|
| `/`        | Returns app name, ConfigMap message, and whether the Secret env var is set (never its value) |
| `/healthz` | Liveness probe endpoint                  |
| `/readyz`  | Readiness probe endpoint                 |

```bash
python3 -m unittest discover -s app -v   # run the tests
APP_MESSAGE="hello locally" python3 app/main.py &
curl http://127.0.0.1:8080/
curl http://127.0.0.1:8080/healthz
```

## Step 2 — Containerize with Docker

```bash
make docker-build          # docker build -t ghcr.io/<you>/kbcicdlab:latest .
make docker-run            # http://127.0.0.1:8080
```

The `Dockerfile` uses `python:3.12-alpine`, creates a non-root `app` user,
sets `PYTHONDONTWRITEBYTECODE`/`PYTHONUNBUFFERED`, exposes 8080, and adds a
`HEALTHCHECK` that hits `/healthz`. `.dockerignore` keeps git metadata, tests,
manifests, and docs out of the image build context.

## Step 3 — Start Minikube

```bash
minikube start --driver=docker
minikube status
kubectl get nodes
```

## Step 4 — Deploy with raw manifests

Load the image into Minikube's own Docker daemon, then apply everything in
`k8s/`:

```bash
docker build -t ghcr.io/chaitanyabfal-ai/kbcicdlab:latest .
minikube image load ghcr.io/chaitanyabfal-ai/kbcicdlab:latest
kubectl apply -f k8s/
```

What each manifest teaches:

- `namespace.yaml` — isolates the lab in the `kbcicdlab` namespace
- `configmap.yaml` — non-sensitive config (`APP_NAME`, `APP_MESSAGE`, `PORT`), injected with `envFrom`
- `secret.yaml` — sensitive value (`DB_PASSWORD`) injected via `secretKeyRef`. The committed value is a placeholder; in real projects create it with `kubectl create secret literal` or an external secrets manager and never commit real values
- `deployment.yaml` — 2 replicas, `livenessProbe` on `/healthz` (restarts the container if it hangs) and `readinessProbe` on `/readyz` (removes the pod from Service endpoints until ready), plus CPU/memory requests and limits
- `service.yaml` — `NodePort` on 30080 so you can reach the app through the Minikube node

Verify:

```bash
kubectl get all -n kbcicdlab
kubectl rollout status deployment/kbcicdlab -n kbcicdlab
kubectl describe deployment kbcicdlab -n kbcicdlab   # see probes + events
kubectl logs -n kbcicdlab -l app.kubernetes.io/name=kbcicdlab

URL=$(minikube service kbcicdlab -n kbcicdlab --url)
curl "$URL/"          # message comes from the ConfigMap
curl "$URL/healthz"   # liveness
curl "$URL/readyz"    # readiness
```

Try it live: edit `APP_MESSAGE` in `k8s/configmap.yaml`, re-apply, and
`kubectl rollout restart deployment/kbcicdlab -n kbcicdlab` — then curl again.
To watch probes work, delete a pod (`kubectl delete pod -n kbcicdlab ...`) and
watch the Deployment recreate it.

## Step 5 — Package it as a Helm chart

The chart in `helm/kbcicdlab/` renders the same Namespace-less workload with
parameterized values:

```bash
helm lint helm/kbcicdlab
helm template kbcicdlab helm/kbcicdlab -n kbcicdlab   # render without a cluster
helm upgrade --install kbcicdlab helm/kbcicdlab -n kbcicdlab --create-namespace
helm list -n kbcicdlab
helm upgrade --install kbcicdlab helm/kbcicdlab -n kbcicdlab \
  --set replicaCount=3 --set config.appMessage="upgraded via Helm" --set image.tag=latest
kubectl rollout status deployment/kbcicdlab -n kbcicdlab
```

Useful values (`helm/kbcicdlab/values.yaml`): `replicaCount`, `image.repository/tag/pullPolicy`,
`service.type/port/nodePort`, `config.*`, `secret.dbPassword`, `probes.*`, `resources`.
Uninstall with `helm uninstall kbcicdlab -n kbcicdlab`.

## Step 6 — The GitHub Actions pipeline

`.github/workflows/ci-cd.yaml` runs on every push to `main` (when app, image,
manifests, chart, or the workflow itself change) and on manual dispatch:

1. **unit-test** — runs `python -m unittest discover -s app`
2. **build-and-push** — Buildx builds the image and pushes it to **GHCR**
   (`ghcr.io/<owner>/kbcicdlab`) tagged with the commit SHA and, on `main`,
   `latest`. It logs in with the built-in `GITHUB_TOKEN`; the workflow-level
   `packages: write` permission is what allows the push. For a public repo this
   needs no extra secrets; for a private package, set the package visibility to
   inherit from the repo in *Package settings*.
3. **helm-check** — `helm lint` + `helm template` so a broken chart fails CI
4. **deploy-minikube** — installs kubectl + Minikube, starts a cluster with the
   docker driver, builds the image locally, loads both tags into Minikube
   (`minikube image load`), applies `k8s/`, pins the Deployment to the commit-SHA
   tag with `kubectl set image`, waits for the rollout, and smoke-tests
   `/healthz`, `/readyz`, and `/` through the NodePort URL

To deploy to a real cluster instead of in-CI Minikube, store a kubeconfig in a
`KUBE_CONFIG` secret and replace the `deploy-minikube` steps with
`azure/k8s-deploy` or `kubectl apply` against that context.

## Cleanup

```bash
make clean          # helm uninstall + kubectl delete -f k8s/ + minikube stop/delete
minikube delete
```

## Troubleshooting

- `ImagePullBackOff` on Minikube → you forgot `minikube image load <image>` (or
  the tag doesn't match); with `imagePullPolicy: IfNotPresent` Minikube uses the
  locally loaded image
- `minikube service ... --url` hangs → check `kubectl get svc -n kbcicdlab` and
  that pods are Ready (`/readyz` must return 200)
- Probes failing → `kubectl describe pod -n kbcicdlab <pod>` shows probe events
  in the pod's Events section
- GHCR push denied in Actions → the workflow needs `permissions: packages: write`
  (already set at the top of the workflow)

## Next steps to extend the lab

Ingress + TLS, HorizontalPodAutoscaler, GitOps (Argo CD / Flux), Sealed
Secrets or External Secrets Operator, Trivy image scanning in CI, multi-environment
promotion with Helm values files per environment.
