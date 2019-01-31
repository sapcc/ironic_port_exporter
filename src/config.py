import logging
import os

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from keystoneauth1 import identity
from keystoneauth1 import session
from neutronclient.v2_0 import client as neutron_client
from ironicclient import client
from backports import configparser

LOG = logging.getLogger(__name__)

def get_neutron_client():
    """
    Neutron client
    """

    auth_parser = get_client_auth()

    auth = identity.Password(auth_url=auth_parser['www_authenticate_uri'],
                             username=auth_parser["username"],
                             password=auth_parser["password"],
                             project_name=auth_parser["project_name"],
                             project_domain_name=auth_parser["user_domain_name"],
                             user_domain_name=auth_parser["user_domain_name"])

    sess = session.Session(auth=auth)
 
    return neutron_client.Client(session=sess)


def get_ironic_client():
    """
    Ironic Client
    """

    auth_parser = get_client_auth()

    kwargs = {'os_username': os.environ.get("OS_IRONIC_USERNAME", "ipmi_exporter"),
              'os_password': os.environ.get("OS_IRONIC_PASSWORD", ""),
              'os_auth_url': auth_parser['www_authenticate_uri'],
              'os_project_name': os.environ.get("OS_PROJECT_NAME", "master"),
              'os_user_domain_name': os.environ.get("OS_USER_DOMAIN_NAME", "Default"),
              'os_project_domain_name': os.environ.get("OS_PROJECT_DOMAIN_NAME", "ccadmin")}
 
    return client.get_client(1, **kwargs)


def get_client_auth():
    v1 = k8s_client.CoreV1Api()

    try:
        cfg = v1.read_namespaced_config_map("neutron-etc", "monsoon3")
        parser = configparser.ConfigParser()
        parser.read_string(cfg.data["neutron.conf"])
        return parser["keystone_authtoken"]
    except IOError:
         LOG.error("Cannot load neutron configmap")

