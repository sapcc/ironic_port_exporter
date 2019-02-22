#!/usr/bin/env python
import pika
import logging
import sys
import json
from threading import Thread
from datetime import datetime

import metrics

LOG = logging.getLogger(__name__)


class Notifications(Thread):


        def __init__(self, user, password, region, routing_key):
                Thread.__init__(self)
                self.routing_key = routing_key
                credentials = pika.PlainCredentials(user, password)
                connection = pika.BlockingConnection(pika.ConnectionParameters(
                        host='ironic-rabbitmq.monsoon3.svc.kubernetes.{0}.cloud.sap'.format(region),
                        credentials=credentials))
                self.channel = connection.channel()
                self.channel.queue_declare(queue='ironic_exporter_notification.{0}'.format(routing_key), auto_delete=True)
                self.nodes_status = {}

                self.channel.queue_bind(exchange='ironic',
                                queue='ironic_exporter_notification.{0}'.format(routing_key),
                                routing_key='ironic_versioned_notifications.{0}'.format(routing_key))
                self.channel.basic_consume(self._callback,
                        queue='ironic_exporter_notification.{0}'.format(routing_key),
                        no_ack=True)


        def run(self):
                self.channel.start_consuming()


        def _callback(self, ch, method, properties, body):
                try:
                        notification = json.loads(body)
                        msg = json.loads(notification['oslo.message'])
                        self._handle_events(msg)
                except KeyError as err:
                        LOG.error("Cannot read ironic event json payload: {0}".format(err))

        
        def _handle_events(self, msg):
                try:
                        event_type = msg['event_type'].split('.')
                        LOG.debug(event_type)
                        timestamp = msg['timestamp']
                        start_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')
                        node_id = msg['payload']['ironic_object.data']['uuid']
                        node_name = msg['payload']['ironic_object.data']['name']
                        provision_state = msg['payload']['ironic_object.data']['provision_state']
                except KeyError as err:
                        LOG.error("Cannot read ironic event json payload: {0}".format(err))
                        return

                if node_id not in self.nodes_status:
                        self.nodes_status[node_id] = {}

                if event_type[3] != 'error':
                        LOG.info('ironic_notification_info: {0}: {1} - {2}. provision_state: {3}'.format(node_name, event_type[2], event_type[3], provision_state))
                        if event_type[3] == 'start':
                                LOG.info("-------S T A R T-------------")
                                self.nodes_status[node_id][event_type[2]] = timestamp
                                LOG.info(self.nodes_status)
                        if event_type[3] == 'end':
                                LOG.info("-------------END------------------", self.nodes_status[node_id])
                                if event_type[2] in self.nodes_status[node_id]:
                                        end_time = datetime.strptime(self.nodes_status[node_id][event_type[2]], '%Y-%m-%d %H:%M:%S.%f')
                                        delta_time = end_time - start_time
                                        LOG.info("-------------END------------------", delta_time.seconds)
                                        metrics.IrionicEventGauge.labels(node_id, node_name, event_type[2]).set(delta_time.seconds)
                elif event_type[3] == 'error':
                        LOG.error('ironic_notification_error: {0}: {1} - {2}. provision_state: {3}'.format(node_name, event_type[2], event_type[3], provision_state))
                        metrics.IrionicEventErrorCounter.labels(node_id, node_name).inc()


