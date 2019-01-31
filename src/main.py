from time import sleep
import logging
import os
 
from keystoneauth1 import identity
from keystoneauth1 import session
from neutronclient.v2_0 import client as neutron_client
from ironicclient import client
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

import config

 
from prometheus_client import start_http_server, Info, CollectorRegistry, Gauge
 
PORT_NUMBER = os.environ.get("PORT_NUMBER", 9456)
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
    PortsGauge = Gauge('openstack_ironic_leftover_ports', 'Neutron ports corresponding to Ironic node ports that were not removed', ['node_uuid'])

 
def get_available_ironic_nodes_uuid(ironic):
    """
 
    """
    LOG.info("Quering Ironic for all non deployed (available) Ironic Nodes") 
    available_nodes = ironic.node.list(maintenance=False,
                                       provision_state='available',
                                       fields=['uuid'])
    LOG.info("Found %d available nodes" % len(available_nodes))
    return available_nodes
 
 
def query_ironic_vs_neutron_ports():
    """
    Do query in Ironic and after in Neutron to find leftover ports
    """
    neutron_cli = config.get_neutron_client()
    ironic_cli = config.get_ironic_client()
 
    all_nodes = get_available_ironic_nodes_uuid(ironic_cli)
    leftover_neutron_ports = {}

    if len(all_nodes) == 0:
        return

    for node in all_nodes:
        LOG.debug("Ironic Node uuid is %s" % node.uuid)
        all_node_ports = ironic_cli.port.list(node=node.uuid)
        leftover_neutron_ports[node.uuid] = []

        for port in all_node_ports:
            LOG.debug("Port MAC address is %s" % port.address)
            neutron_ports = neutron_cli.list_ports(mac_address=port.address)['ports']

            if len(neutron_ports) == 1:
                LOG.debug("The ID of the leftover port is %s" % neutron_ports[0]['id'])
                leftover_neutron_ports[node.uuid].append(neutron_ports[0]['id'])
 
            elif len(neutron_ports) > 1:
                LOG.error("There is more than on Neutron port with mac %s" % port.address)
                for leftover_port in neutron_ports:
                    LOG.info("The ID of the leftover port is %s" % leftover_port['id'])
                    leftover_neutron_ports[node.uuid].append(leftover_port['id'])
            
        PortsGauge.labels(node.uuid).set(len(leftover_neutron_ports[node.uuid]))
 
 
if __name__ == "__main__":
    """
    Main function
    """
    setup_logging()
    setup_k8s()
    setup_prometheus()
 
    # Set a server to export (expose to prometheus) the data (in a thread)
    try:
        start_http_server(PORT_NUMBER)
        while True:
            query_ironic_vs_neutron_ports()
            sleep(15)
    except KeyboardInterrupt:
        exit(0)