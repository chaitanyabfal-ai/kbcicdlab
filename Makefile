REGISTRY  ?= ghcr.io
OWNER     ?= chaitanyabfal-ai
IMAGE     ?= $(REGISTRY)/$(OWNER)/kbcicdlab
TAG       ?= latest
NAMESPACE ?= kbcicdlab
CHART     ?= helm/kbcicdlab
RELEASE   ?= kbcicdlab

.PHONY: test docker-build docker-run minikube-start deploy status logs port-forward \
        helm-lint helm-template helm-install helm-uninstall clean

test:
	python3 -m unittest discover -s app -v

docker-build:
	docker build -t $(IMAGE):$(TAG) .

docker-run:
	docker run --rm -p 8080:8080 -e APP_MESSAGE="local docker run" $(IMAGE):$(TAG)

minikube-start:
	minikube start --driver=docker

deploy:
	kubectl apply -f k8s/

status:
	kubectl get all -n $(NAMESPACE)
	kubectl rollout status deployment/$(RELEASE) -n $(NAMESPACE)

logs:
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/name=$(RELEASE) --tail=50

port-forward:
	kubectl port-forward -n $(NAMESPACE) svc/$(RELEASE) 8080:80

helm-lint:
	helm lint $(CHART)

helm-template:
	helm template $(RELEASE) $(CHART) -n $(NAMESPACE)

helm-install:
	helm upgrade --install $(RELEASE) $(CHART) -n $(NAMESPACE) --create-namespace

helm-uninstall:
	helm uninstall $(RELEASE) -n $(NAMESPACE) || true

clean: helm-uninstall
	kubectl delete -f k8s/ --ignore-not-found=true
	-minikube stop
	-minikube delete
