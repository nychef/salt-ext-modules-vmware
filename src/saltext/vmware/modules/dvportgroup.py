# Copyright 2022 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0
import json
import logging

import saltext.vmware.utils.connect as connect
import saltext.vmware.utils.vsphere as utils_vmware

log = logging.getLogger(__name__)

try:
    from pyVmomi import vim, vmodl, VmomiSupport

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

__virtualname__ = "vmware_dvportgroup"
__proxyenabled__ = ["vmware_dvportgroup"]


def __virtual__():
    if not HAS_PYVMOMI:
        return False, "Unable to import pyVmomi module."
    return __virtualname__


def get(switch_name, portgroup_id=None, host_name=None, service_instance=None, profile=None):
    """
    Get distributed portgroup from a distributed switch optionally from a host.

    service_instance
        Service instance object to access vCenter

    switch_name
        Name of the distributed switch.

    portgroup_id
        Portgroup key or name. (Optional).
    
    host_name
        Name of the ESXi host.  (optional).

    service_instance
        Use this vCenter service connection instance instead of creating a new one. (optional)

    profile
        Profile to use (optional)
    """
    ret = []

    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    switch_ref = utils_vmware._get_dvs(service_instance=service_instance, dvs_name=switch_name)
    if switch_ref:
        for portgroup in switch_ref.portgroup:
            pg = {}
            pg["name"] = portgroup.config.name
            pg["key"] = portgroup.config.key
            pg["vlan"] = portgroup.config.defaultPortConfig.vlan.vlanId
            pg["ports"] = portgroup.config.numPorts
            pg["pnic"] = []
            if host_name:
                for host in portgroup.config.distributedVirtualSwitch.config.host:
                    if host.config.host.name == host_name:
                        for pnic in host.config.backing.pnicSpec:
                            pg["pnic"].append(pnic.pnicDevice)

            if portgroup_id and portgroup_id in [portgroup.config.name, portgroup.config.key]:
                ret.append(pg)
            elif not portgroup_id:
                ret.append(pg)


        ret = json.loads(json.dumps(ret, cls=VmomiSupport.VmomiJSONEncoder))
    return ret
