#!/usr/bin/env python
import pika
import logging
import sys
import json
from threading import Thread
from datetime import datetime
from retry import retry

import metrics

LOG = logging.getLogger(__name__)


class Notifications(Thread):


        def __init__(self, user, password, region, routing_key):
                Thread.__init__(self)
                self.routing_key = routing_key
                credentials = pika.PlainCredentials(user, password)
                self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                        host='ironic-rabbitmq.monsoon3.svc.kubernetes.{0}.cloud.sap'.format(region),
                        credentials=credentials))


        @retry(pika.exceptions.AMQPConnectionError, delay=5, jitter=(1, 3))
        def run(self):
                self.channel = self.connection.channel()
                self.channel.queue_declare(queue='ironic_exporter_notification.{0}'.format(self.routing_key), auto_delete=True)
                self.nodes_status = {}

                self.channel.queue_bind(exchange='ironic',
                                queue='ironic_exporter_notification.{0}'.format(self.routing_key),
                                routing_key='ironic_versioned_notifications.{0}'.format(self.routing_key))
                self.channel.basic_consume(self._callback,
                        queue='ironic_exporter_notification.{0}'.format(self.routing_key),
                        no_ack=True)

                try:
                        self.channel.start_consuming()
                # Don't recover connections closed by server
                except pika.exceptions.ConnectionClosedByBroker:
                        pass


        def _callback(self, ch, method, properties, body):
                try:
                        notification = json.loads(body)
                        msg = json.loads(notification['oslo.message'])
                        self._handle_events(msg)
                        self._set_provision_state(msg)
                except KeyError as err:
                        LOG.error("Cannot read ironic event json payload: {0}".format(err))


        def _set_provision_state(self, msg):
                provision_state = msg['payload']['ironic_object.data']['provision_state']
                node_id = msg['payload']['ironic_object.data']['uuid']
                node_name = msg['payload']['ironic_object.data']['name']
                if provision_state in metrics.Provision_States:
                        metrics.IronicProvisionState.labels(node_id, node_name).set(metrics.Provision_States[provision_state])

        
        def _handle_events(self, msg):
                try:
                        event_type = msg['event_type'].split('.')
                        LOG.debug(event_type)
                        timestamp = msg['timestamp']
                        date_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')
                        data = msg['payload']['ironic_object.data']
                        node_id = data['uuid']
                        node_name = data['name']
                        provision_state = data['provision_state']
                except KeyError as err:
                        LOG.error("Cannot read ironic event json payload: {0}".format(err))
                        return

                if node_name is None:
                        return

                if node_id not in self.nodes_status:
                        self.nodes_status[node_id] = {}

                if event_type[3] != 'error':
                        LOG.info('ironic_notification_info: {0}: {1} - {2} - {3}. provision_state: {4}'.format(node_name, event_type[1], event_type[2], event_type[3], provision_state))
                        if event_type[3] == 'start':
                                self.nodes_status[node_id][event_type[2]] = timestamp
                                LOG.debug(self.nodes_status)
                        if event_type[3] == 'end' or event_type[3] == 'success':
                                LOG.info(self.nodes_status[node_id])
                                if event_type[2] in self.nodes_status[node_id]:
                                        start_time = datetime.strptime(self.nodes_status[node_id][event_type[2]], '%Y-%m-%d %H:%M:%S.%f')
                                        delta_time = date_time - start_time
                                        event_label = '{0}_{1}'.format(event_type[1], event_type[2])
                                        metrics.IrionicEventGauge.labels(node_id, node_name, event_label).set(delta_time.seconds)
                elif event_type[3] == 'error':
                        target_provision_state = data['target_provision_state']
                        LOG.error('ironic_notification_error: {0}: {1} - {2} - {3}. provision_state: {4}. target_provision_state:{5}'.format(node_name, event_type[1], event_type[2], event_type[3], provision_state, target_provision_state))
                        metrics.IrionicEventErrorCounter.labels(node_id, node_name).inc()
