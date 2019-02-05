IMAGE   ?= hub.global.cloud.sap/monsoon/ironic-exporter
VERSION = $(shell git rev-parse --verify HEAD | head -c 8)


build: 
	docker build -t $(IMAGE):$(VERSION) .

push: build
	docker push $(IMAGE):$(VERSION)