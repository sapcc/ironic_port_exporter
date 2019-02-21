
#!/usr/bin/env python
import pika
import logging
import sys
import json
from threading import Thread

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
                print(properties)
                print(method)
                notification = json.loads(body)
                msg = json.loads(notification['oslo.message'])
                try:
                        event_type = msg['event_type'].split('.')
                        timestamp = msg['timestamp']
                        node_id = msg['payload']['ironic_object.data']['uuid']
                        provision_state = msg['payload']['ironic_object.data']['provision_state']
                        LOG.debug(event_type)
                        self._handle_events(event_type, timestamp, node_id)
                except KeyError as err:
                        LOG.error("Cannot read ironic event json payload: {0}".format(err))

        
        def _handle_events(self, event_type, time, node_id):
                if event_type[3] != 'error':
                        LOG.info('Ironic Node {0}: {1} - {2}'.format(node_id, event_type[2], event_type[3]))
                        #if event_type[3] == 'start':
                                #metrics.IrionicEventGauge.labels(node_id, event_type[2]).set(1)
                        if event_type[3] == 'end':
                                metrics.IrionicEventGauge.labels(node_id, event_type[2]).inc()
                elif event_type[3] == 'error':
                        LOG.error('Ironic Node {0}: {1} - {2}'.format(node_id, event_type[2], event_type[3]))
                        metrics.IrionicEventErrorGauge.labels(node_id).inc()


