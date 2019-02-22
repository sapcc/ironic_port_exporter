from prometheus_client import Gauge, Counter


PortsGauge = Gauge('openstack_ironic_leftover_ports', 'Neutron ports corresponding to Ironic node ports that were not removed', ['node_uuid'])
CallbackGauge = Gauge('openstack_ironic_callback_state', 'Ironic node in wait call-back state', ['node_uuid'])
IrionicEventGauge = Counter('openstack_ironic_event', 'Ironic node events', ['node_uuid', 'node_name', 'event'])
IrionicEventErrorGauge = Counter('openstack_ironic_errors', 'Ironic node errors', ['node_uuid', 'node_name'])