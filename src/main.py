from time import sleep
import logging
import os
import sys
 
from keystoneauth1 import identity
from keystoneauth1 import session
from neutronclient.v2_0 import client as neutron_client
from prometheus_client import start_http_server, Info, CollectorRegistry, Gauge
from ironicclient import client
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

import config

PORT_NUMBER = os.environ.get("PORT_NUMBER", 9191)
LOG = logging.getLogger(__name__)
PortsGauge = None


def setup_logging():
    logging.basicConfig(format='%(asctime)-15s %(process)d %(levelname)s %(filename)s:%(lineno)d %(message)s',
                        level=os.environ.get("LOGLEVEL", "INFO"))
 

def setup_k8s():
    try:
        k8s_config.load_kube_config()

    except IOError:
        os.environ['KUBERNETES_SERVICE_HOST'] = os.environ['KUBERNETES_SERVICE_HOST'] or 'kubernetes.default'
        os.environ['KUBERNETES_SERVICE_PORT'] = os.environ['KUBERNETES_SERVICE_PORT'] or 443
        k8s_config.load_incluster_config()


def setup_prometheus():
    port_info = Info('openstack_ironic_leftover_ports',
                     'Neutron ports corresponding to Ironic node ports that were not removed')
    port_info.info({'version': os.environ.get("OS_VERSION", '')})
    registry = CollectorRegistry()
    registry.register(port_info)
    global PortsGauge  
    PortsGauge = Gauge('openstack_ironic_leftover_ports', 'Neutron ports corresponding to Ironic node ports that were not removed', ['node_uuid', 'provision_state'])

 
def get_available_ironic_nodes_uuid(ironic):
    """
 
    """
    LOG.debug("Quering Ironic for all non deployed (available) Ironic Nodes") 
    available_nodes = ironic.node.list(maintenance=False,
                                       fields=['uuid', 'provision_state', 'maintenance'])
    LOG.debug("Found %d available nodes" % len(available_nodes))
    return available_nodes
 

def query_ironic_vs_neutron_ports(neutron_cli, ironic_cli):
    """
    Do query in Ironic and after in Neutron to find leftover ports
    """

    all_nodes = get_available_ironic_nodes_uuid(ironic_cli)
    leftover_neutron_ports = {}

    if len(all_nodes) == 0:
        return

    for node in all_nodes:
        LOG.info("Ironic Node uuid is {0}".format(node.uuid))
        if node.provision_state != 'available':
            LOG.debug("Remove Ironic Node uuid {0}".format(node.provision_state))
            try:
                PortsGauge.labels(node.uuid, node.provision_state).set(0)
            except KeyError as err:
                LOG.error("Cannot set Ironic Node label err: {0}".format(err))
            continue

        all_node_ports = ironic_cli.port.list(node=node.uuid)
        leftover_neutron_ports[node.uuid] = []

        for port in all_node_ports:
            LOG.debug("Port MAC address is {}".format(port.address))
            neutron_ports = neutron_cli.list_ports(mac_address=port.address)['ports']

            if len(neutron_ports) == 1:
                LOG.info("node_uuid: {0}: leftover port_id: {1}".format(node.uuid, neutron_ports[0]['id']))
                leftover_neutron_ports[node.uuid].append(neutron_ports[0]['id'])
 
            elif len(neutron_ports) > 1:
                LOG.error("There is more than on Neutron port with mac {0}".format(port.address))
                for leftover_port in neutron_ports:
                    LOG.info("node_uuid: {0}: leftover port_id: {1}".format(node.uuid, leftover_port['id']))
                    leftover_neutron_ports[node.uuid].append(leftover_port['id'])
        
        try:
            PortsGauge.labels(node.uuid, node.provision_state).set(len(leftover_neutron_ports[node.uuid]))
         except KeyError as err:
            LOG.error("Cannot set Ironic Node label err: {0}".format(err))

if __name__ == "__main__":
    """
    Main function
    """
    setup_logging()
    setup_k8s()
    setup_prometheus()

    try:
        neutron_cli = config.get_neutron_client()
        ironic_cli = config.get_ironic_client()
    except k8s_client.rest.ApiException as err:
        if err.status == 404:
            LOG.error("Neutron-etc configmap not found!")
            sys.exit(1)
        else:
            LOG.error("Cannot load neutron configmap: {0}".format(err))
            sys.exit(1)

    # Set a server to export (expose to prometheus) the data (in a thread)
    try:
        start_http_server(int(PORT_NUMBER), addr='0.0.0.0')
        while True:
            LOG.info("-----------------------Start Query------------------------")
            query_ironic_vs_neutron_ports(neutron_cli, ironic_cli)
            sleep(50)
    except KeyboardInterrupt:
        exit(0)
