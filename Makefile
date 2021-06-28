IMAGE   ?=  keppel.eu-de-1.cloud.sap/ccloud/ironic-exporter
VERSION = $(shell git rev-parse --verify HEAD | head -c 8)


build: 
	docker build -t $(IMAGE):$(VERSION) .

push: build
	docker push $(IMAGE):$(VERSION)