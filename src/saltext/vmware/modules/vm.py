# SPDX-License-Identifier: Apache-2.0
import json
import logging

import salt.exceptions
import salt.utils.platform
import saltext.vmware.utils.common as utils_common
import saltext.vmware.utils.connect as connect
import saltext.vmware.utils.datacenter as utils_datacenter
import saltext.vmware.utils.datastore as utils_datastore
import saltext.vmware.utils.vm as utils_vm
import saltext.vmware.utils.vsphere as utils_vmware

log = logging.getLogger(__name__)

try:
    from pyVmomi import vim, VmomiSupport

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

__virtualname__ = "vmware_vm"
__proxyenabled__ = ["vmware_vm"]
__func_alias__ = {"list_": "list"}


def __virtual__():
    return __virtualname__


def list_(
    service_instance=None, datacenter_name=None, cluster_name=None, host_name=None, profile=None
):
    """
    Returns virtual machines.

    datacenter_name
        Filter by this datacenter name (required when cluster is specified)

    cluster_name
        Filter by this cluster name (optional)

    host_name
        Filter by this host name (optional)

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.list
    """
    log.debug("Running vmware_vm.list")
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )
    return utils_vm.list_vms(
        service_instance=service_instance,
        host_name=host_name,
        cluster_name=cluster_name,
        datacenter_name=datacenter_name,
    )


def list_templates(service_instance=None, profile=None):
    """
    Returns virtual machines tempates.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.list_templates
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )
    return utils_vm.list_vm_templates(service_instance)


def path(vm_name, service_instance=None, profile=None):
    """
    Returns specified virtual machine path.

    vm_name
        The name of the virtual machine.

    service_instance
        The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.path vm_name=vm01
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )
    vm_ref = utils_common.get_mor_by_property(
        service_instance,
        vim.VirtualMachine,
        vm_name,
    )
    return utils_common.get_path(vm_ref, service_instance)


def _deploy_ovf(name, host_name, ovf, service_instance=None, profile=None):
    """
    Helper fuctions that takes in a OVF file to create a virtual machine.

    Returns virtual machine reference.

    name
        The name of the virtual machine to be created.

    host_name
        The name of the esxi host to create the vitual machine on.

    ovf_path
        The path to the Open Virtualization Format that contains a configuration of a virtual machine.

    service_instance
        Use this vCenter service connection instance instead of creating a new one. (optional).

    profile
        Profile to use (optional)
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    vms = list_(service_instance)
    if name in vms:
        raise salt.exceptions.CommandExecutionError("Duplicate virtual machine name.")

    content = service_instance.content
    manager = content.ovfManager
    spec_params = vim.OvfManager.CreateImportSpecParams(entityName=name)

    resources = utils_common.deployment_resources(host_name, service_instance)

    import_spec = manager.CreateImportSpec(
        ovf, resources["resource_pool"], resources["destination_host"].datastore[0], spec_params
    )
    errors = [e.msg for e in import_spec.error]
    if errors:
        log.exception(errors)
        raise salt.exceptions.VMwareApiError(errors)
    vm_ref = utils_vm.create_vm(
        name,
        import_spec.importSpec.configSpec,
        resources["datacenter"].vmFolder,
        resources["resource_pool"],
        resources["destination_host"],
    )
    return vm_ref


def deploy_ovf(vm_name, host_name, ovf_path, service_instance=None):
    """
    Deploy a virtual machine from an OVF

    vm_name
        The name of the virtual machine to be created.

    host_name
        The name of the esxi host to create the vitual machine on.

    ovf_path
        The path to the Open Virtualization Format that contains a configuration of a virtual machine.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.deploy_ovf vm_name=vm01 host_name=host1 ovf_path=/tmp/appliance.ovf
    """
    ovf = utils_vm.read_ovf_file(ovf_path)
    _deploy_ovf(vm_name, host_name, ovf, service_instance)
    return {"deployed": True}


def deploy_ova(vm_name, host_name, ova_path, service_instance=None):
    """
    Deploy a virtual machine from an OVA

    vm_name
        The name of the virtual machine to be created.

    host_name
        The name of the esxi host to create the vitual machine on.

    ova_path
        The path to the Open Virtualization Appliance that contains a compressed configuration of a virtual machine.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.deploy_ova vm_name=vm01 host_name=host1 ova_path=/tmp/appliance.ova
    """
    ovf = utils_vm.read_ovf_from_ova(ova_path)
    _deploy_ovf(vm_name, host_name, ovf, service_instance)
    return {"deployed": True}


def deploy_template(vm_name, template_name, host_name, service_instance=None, profile=None):
    """
    Deploy a virtual machine from a template virtual machine.

    vm_name
        The name of the virtual machine to be created.

    template_name
        The name of the template to clone from.

    host_name
        The name of the esxi host to create the vitual machine on.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.deploy_template vm_name=vm01 template_name=template1 host_name=host1
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    vms = list_(service_instance)
    if vm_name in vms:
        raise salt.exceptions.CommandExecutionError("Duplicate virtual machine name.")

    template_vms = list_templates(service_instance)
    if template_name not in template_vms:
        raise salt.exceptions.CommandExecutionError("Template does not exist.")

    template = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, template_name)
    resources = utils_common.deployment_resources(host_name, service_instance)

    relospec = vim.vm.RelocateSpec()
    relospec.pool = resources["resource_pool"]

    clonespec = vim.vm.CloneSpec()
    clonespec.location = relospec

    utils_vm.clone_vm(vm_name, resources["datacenter"].vmFolder, template, clonespec)
    return {"deployed": True}


def info(vm_name=None, service_instance=None, profile=None):
    """
    Return basic info about a vSphere VM guest

    vm_name
        (optional) The name of the virtual machine to get info on.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.info vm_name=vm01
    """
    vms = []
    info = {}
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    if vm_name:
        vms.append(
            utils_common.get_mor_by_property(
                service_instance,
                vim.VirtualMachine,
                vm_name,
            )
        )

    else:
        for dc in service_instance.content.rootFolder.childEntity:
            for i in dc.vmFolder.childEntity:
                if isinstance(i, vim.VirtualMachine):
                    vms.append(i)

    for vm in vms:
        if not vm:
            info[vm_name] = f"{vm_name} not found"
            info["success"] = False
            continue

        datacenter_ref = utils_common.get_parent_type(vm, vim.Datacenter)
        mac_address = utils_vm.get_mac_address(vm)
        network = utils_vm.get_network(vm)
        tags = []
        for tag in vm.tag:
            tags.append(tag.name)
        folder_path = utils_common.get_path(vm, service_instance)
        info[vm.summary.config.name] = {
            "guest_name": vm.summary.config.name,
            "path": vm.summary.config.vmPathName,
            "guest_fullname": vm.summary.guest.guestFullName,
            "power_state": vm.summary.runtime.powerState,
            "ip_address": vm.summary.guest.ipAddress,
            "mac_address": mac_address,
            "uuid": vm.summary.config.uuid,
            "vm_network": network,
            "esxi_hostname": vm.summary.runtime.host.name,
            "datacenter": datacenter_ref.name,
            "cluster": vm.summary.runtime.host.parent.name,
            "tags": tags,
            "folder": folder_path,
            "moid": vm._moId
        }
    return info


def power_state(vm_name, state, datacenter_name=None, service_instance=None, profile=None):
    """
    Manages the power state of a virtual machine.

    vm_name
        The name of the virtual machine.

    state
        The state you want the specified virtual machine in (powered-on,powered-off,suspend,reset).

    datacenter_name
        (optional) The name of the datacenter containing the virtual machine you want to manage.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.power_state vm_name=vm01 state=powered-on datacenter_name=dc1
    """
    log.trace(f"Managing power state of virtual machine {vm_name} to {state}")
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    if datacenter_name:
        dc_ref = utils_common.get_mor_by_property(service_instance, vim.Datacenter, datacenter_name)
        vm_ref = utils_common.get_mor_by_property(
            service_instance, vim.VirtualMachine, vm_name, "name", dc_ref
        )
    else:
        vm_ref = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, vm_name)

    if vm_ref == None:
        return (False, "vm doesn't exist or not found")
    if state == "powered-on" and vm_ref.summary.runtime.powerState == "poweredOn":
        result = {
            "comment": "Virtual machine is already powered on",
            "changes": {"state": vm_ref.summary.runtime.powerState},
        }
        return result
    elif state == "powered-off" and vm_ref.summary.runtime.powerState == "poweredOff":
        result = {
            "comment": "Virtual machine is already powered off",
            "changes": {"state": vm_ref.summary.runtime.powerState},
        }
        return result
    elif state == "suspend" and vm_ref.summary.runtime.powerState == "suspended":
        result = {
            "comment": "Virtual machine is already suspended",
            "changes": {"state": vm_ref.summary.runtime.powerState},
        }
        return result
    result_ref_vm = utils_vm.power_cycle_vm(vm_ref, state)
    result = {
        "comment": f"Virtual machine {state} action succeeded",
        "changes": {"state": f"{vm_name} -> {result_ref_vm.summary.runtime.powerState}"},
    }
    return result


def boot_manager(
    vm_name,
    order=["cdrom", "disk", "ethernet", "floppy"],
    delay=0,
    enter_bios_setup=False,
    retry_delay=0,
    efi_secure_boot_enabled=False,
    service_instance=None,
    profile=None,
):
    """
    Manage boot option for a virtual machine

    vm_name
        The name of the virtual machine.

    order
        (List of strings) Boot order of devices. Acceptable strings: cdrom, disk, ethernet, floppy

    delay
        (integer, optional) Boot delay. When powering on or resetting, delay boot order by given milliseconds. Defaults to 0.

    enter_bios_setup
        (boolean, optional) During the next boot, force entry into the BIOS setup screen. Defaults to False.

    retry_delay
        (integer, optional) If the VM fails to find boot device, automatically retry after given milliseconds. Defaults to 0 (do not retry).

    efi_secure_boot_enabled
        (boolean, optional) Defaults to False.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.boot_manager vm_name=vm01 order='["cdrom", "disk", "ethernet"]' delay=5000 enter_bios_setup=False retry_delay=5000 efi_secure_boot_enabled=False
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    vm = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, vm_name)

    boot_order_list = utils_vm.options_order_list(vm, order)

    # we removed the ability to individually set bootRetryEnabled, easily implemented if asked for
    input_opts = {
        "bootOrder": boot_order_list,
        "bootDelay": delay,
        "enterBIOSSetup": enter_bios_setup,
        "bootRetryEnabled": bool(retry_delay),
        "bootRetryDelay": retry_delay,
        "efiSecureBootEnabled": efi_secure_boot_enabled,
    }

    if utils_vm.compare_boot_options(input_opts, vm.config.bootOptions):
        return {"status": "already configured this way"}
    ret = utils_vm.change_boot_options(vm, input_opts)

    return ret


def create_snapshot(
    vm_name,
    snapshot_name,
    description="",
    include_memory=False,
    quiesce=False,
    datacenter_name=None,
    service_instance=None,
    profile=None,
):
    """
    Create snapshot of given vm.

    vm_name
        The name of the virtual machine.

    snapshot_name
        The name for the snapshot being created. Not unique

    description
        Description for the snapshot.

    include_memory
        (boolean, optional) If TRUE, a dump of the internal state of the virtual machine (basically a memory dump) is included in the snapshot.

    quiesce
        (boolean, optional) If TRUE and the virtual machine is powered on when the snapshot is taken, VMware Tools is used to quiesce the file system in the virtual machine.

    datacenter_name
        (optional) The name of the datacenter containing the virtual machine.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.create_snapshot vm_name=vm01 snapshot_name=backup_snapshot_1 description="This snapshot is a backup of vm01" include_memory=False quiesce=True datacenter_name=dc1
    """

    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    if datacenter_name:
        dc_ref = utils_common.get_mor_by_property(service_instance, vim.Datacenter, datacenter_name)
        vm_ref = utils_common.get_mor_by_property(
            service_instance, vim.VirtualMachine, vm_name, "name", dc_ref
        )
    else:
        vm_ref = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, vm_name)

    snapshot = utils_vm.create_snapshot(vm_ref, snapshot_name, description, include_memory, quiesce)

    if isinstance(snapshot, vim.vm.Snapshot):
        return {"snapshot": "created", "success": True}
    else:
        return {"snapshot": "failed to create", "success": False}


def destroy_snapshot(
    vm_name,
    snapshot_name,
    snapshot_id=None,
    remove_children=False,
    datacenter_name=None,
    service_instance=None,
    profile=None,
):
    """
    Destroy snapshot of given vm.

    vm_name
        The name of the virtual machine.

    snapshot_name
        The name for the snapshot being destroyed. Not unique

    snapshot_id
        (optional) ID of snapshot to be destroyed.

    remove_children
        (optional, Bool) Remove snapshots below snapshot being removed in tree.

    datacenter_name
        (optional) The name of the datacenter containing the virtual machine.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.destroy_snapshot vm_name=vm01 snapshot_name=backup_snapshot_1 snapshot_id=1 remove_children=False datacenter_name=dc1
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    if datacenter_name:
        dc_ref = utils_common.get_mor_by_property(service_instance, vim.Datacenter, datacenter_name)
        vm_ref = utils_common.get_mor_by_property(
            service_instance, vim.VirtualMachine, vm_name, "name", dc_ref
        )
    else:
        vm_ref = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, vm_name)

    snap_ref = utils_vm.get_snapshot(vm_ref, snapshot_name, snapshot_id)
    utils_vm.destroy_snapshot(snap_ref.snapshot, remove_children)
    return {"snapshot": "destroyed"}


def snapshot(vm_name, datacenter_name=None, service_instance=None, profile=None):
    """
    Return info about a virtual machine snapshots

    vm_name
        (optional) The name of the virtual machine to get info on.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.snapshot vm_name=vm01 datacenter_name=dc1
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    if datacenter_name:
        dc_ref = utils_common.get_mor_by_property(service_instance, vim.Datacenter, datacenter_name)
        vm_ref = utils_common.get_mor_by_property(
            service_instance, vim.VirtualMachine, vm_name, "name", dc_ref
        )
    else:
        vm_ref = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, vm_name)

    snapshots = utils_vm.get_snapshots(vm_ref)

    return {"snapshots": snapshots}


def relocate(
    vm_name,
    new_host_name,
    datastore_name,
    datacenter_name=None,
    service_instance=None,
    profile=None,
):
    """
    Relocates a virtual machine to the location specified.

    vm_name
        The name of the virtual machine to relocate.

    new_host_name
        The name of the host you want to move the virtual machine to.

    datastore_name
        The name of the datastore you want to move the virtual machine to.

    datacenter_name
        The name of the datacenter containing the datastore.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.relocate vm_name=vm01 new_host_name=host1 datastore_name=ds01
    """
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )
    vm_ref = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, vm_name)
    resources = utils_common.deployment_resources(new_host_name, service_instance)
    assert isinstance(datastore_name, str)
    datastores = utils_datastore.get_datastores(
        service_instance, datastore_name=datastore_name, datacenter_name=datacenter_name
    )
    datastore_ref = datastores[0] if datastores else None
    ret = utils_vm.relocate(
        vm_ref, resources["destination_host"], datastore_ref, resources["resource_pool"]
    )
    if ret == "success":
        return {"virtual_machine": "moved", "success": True}
    return {"virtual_machine": "failed to move", "success": False}


def get_mks_ticket(vm_name, ticket_type, service_instance=None, profile=None):
    """
    Get ticket of virtual machine of passed object type.

    vm_name
        The name of the virtual machine which has tickets. VM names can be
        found in ``vmware_vm.list``.

    ticket_type
        Type of ticket - device, guestControl, guestIntegrity, mks, or webmks.

        See https://vdc-download.vmware.com/vmwb-repository/dcr-public/3325c370-b58c-4799-99ff-58ae3baac1bd/45789cc5-aba1-48bc-a320-5e35142b50af/doc/vim.VirtualMachine.TicketType.html

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.get_mks_ticket vm_name=vm01 ticket_type=webmks
    """
    if service_instance is None:
        service_instance = connect.get_service_instance(config=__opts__, profile=profile)

    log.info(f"Acquiring ticket {ticket_type} for {vm_name}")
    vm_ref = utils_common.get_mor_by_property(service_instance, vim.VirtualMachine, vm_name)
    if vm_ref:
        ticket = vm_ref.AcquireTicket(ticket_type)
        return json.loads(json.dumps(ticket, cls=VmomiSupport.VmomiJSONEncoder))
    return {}

def unregister(vm_name, shutdown=False, service_instance=None, profile=None):
    """
    Unregisters a VM

    vm_name
        The name of the virtual machine to unregister.

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.unregister_vm vm_name=vm01
    """
    ret = "No changes made"
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    log.debug("running vmware_vm.unregister")
    vm = utils_common.get_mor_by_property(
            service_instance,
            vim.VirtualMachine,
            vm_name,
         )

    if vm.summary.runtime.powerState == "poweredOn":
        if shutdown:
            try:
                utils_vm.shutdown(vm)
            except Exception as err:
                return (False, f"error powering off vm before unregistration: {err}")   
        else:
            return (False, "VM must be powered off")

    try:
        log.debug(f"unregistering {vm.name}")
        utils_vm.unregister_vm(vm)
        ret = {
            "success": True,
        }
    except Exception as err:
        ret = {
            "success": False, 
            "comment": "Unregsitering VM failed",
            "error": f"error unregistering vm: {err}"
        }

    return ret

def register(datacenter_name, pool_name, vm_name, vmx_path, folder_name=None, service_instance=None, profile=None):
    """
    registers a VM

    datacenter_name
        The name of the datacenter to place the VM in

    pool_name
        The name of the resource pool to place the VM in

    vm_name
        The name of the virtual machine to register.

    vmx_path
        The path to the vmx file containing the machine info

    folder_name
        The name of the folder to place the VM in

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.info vm_name=vm01
    """
    ret = "No changes made"
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    log.debug("running vmware_vm.register")
    datacenter = utils_datacenter.get_datacenter(service_instance, datacenter_name)
    pool = utils_common.get_resource_pools(service_instance, [pool_name], datacenter_name)
    
    if len(pool) > 1:
        return {
            "success": False, 
            "comment": "register VM failed",
            "error": "too many pools"
        }
    elif len(pool) == 0:
        return {
            "success": False,
            "comment": "register VM failed",
            "error": f"pool {pool_name} not found"
        }
    else:
        pool = pool[0]

    try:
        log.debug(f"registering {vm_name}")
        ret = utils_vm.register_vm(datacenter, vm_name, vmx_path, pool, folder_name, service_instance)
        if not isinstance(ret, dict):
            ret = True
    except Exception as err:
        ret = {
            "success": False,
            "comment": "register VM failed",
            "error": f"error registering vm: {err}"
        }

    return ret


def set_ip_info(ip, subnet, gw, dns, domain, vm_name, os=None, service_instance=None, profile=None):
    """
    sets IP info for a VM (VM must be powered off first)

    ip
        The IP address to set
    
    subnet
        The subnet mask to set
    
    gw
        The gateway to set

    dns
        (list) "[dns1, dns2]"

    domain
        dns domain for the NIC

    vm_name
        The name of the VM to modify

    os
        The VM of the guest, if the guest is newly imported this field must be used (Optional)

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.set_ip_info ip=192.168.2.2 subnet=255.255.255.0 gw=192.168.2.1 dns=(192.168.2.10,192.168.2.11) vm_name=vm01
    """


    ret = "No changes made"
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    log.debug("running vmware_vm.set_ip_info")

    vm = utils_common.get_mor_by_property(
                service_instance,
                vim.VirtualMachine,
                vm_name,
            )
    if vm.summary.runtime.powerState == "poweredOn":
        return {
            "success": False,
            "comment": "set_ip_info failed",
            "error": "VM must be powered off"
        }

    if vm.summary.guest.guestFullName:
        vm_os = vm.summary.guest.guestFullName.lower()
    elif os:
        vm_os = os
    else:
        return {
            "success": False, 
            "comment": "set_ip_info failed",
            "error": "guestFullName is empty AND os was not passed"
        }

    if 'linux' in vm_os:
        identity = vim.vm.customization.LinuxPrep()
        identity.hostName = vim.vm.customization.FixedName()
        identity.hostName.name = vm_name
        identity.domain = domain
    elif 'windows' in vm_os:
        identity = vim.vm.customization.Sysprep()
        # there are likely some other settings needed here
    else:
        return {
            "success": False, 
            "comment": "set_ip_info failed",
            "error": "Unsupported OS for IP customization"
        }

    adapter_map = {}
    adapter_count = 0
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            adapter_count += 1
            adapter_map[device.deviceInfo.label] = device

    if adapter_count > 1:
        return {
            "success": False, 
            "comment": "set_ip_info failed",
            "error": "Only a single NIC is supported for IP customization"
        }

    ip_settings = vim.vm.customization.IPSettings()
    ip_settings.ip = vim.vm.customization.FixedIp()
    ip_settings.ip.ipAddress = ip
    ip_settings.subnetMask = subnet
    ip_settings.gateway = [gw]
    ip_settings.dnsServerList = list(dns)
    ip_settings.dnsDomain = domain
 
    globalip = vim.vm.customization.GlobalIPSettings()
    globalip.dnsServerList = list(dns)
    globalip.dnsSuffixList = [domain]

    adapter = vim.vm.customization.AdapterMapping()
    adapter.adapter = ip_settings

    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            adapter_map[device.deviceInfo.label] = adapter

    spec = vim.vm.customization.Specification()
    spec.identity = identity
    spec.globalIPSettings = globalip
    spec.nicSettingMap = list(adapter_map.values())

    try:   
        utils_vm.customize_vm(vm, spec)
        ret = True
    except Exception as err:
        ret = {
            "success": False, 
            "comment": "set_ip_info failed",
            "error": f"error updating ip: {err}"
        }

    return ret


def set_dvport(vm_name, dvswitch_name, dport_group_name, service_instance=None, profile=None):
    """
    Sets the Distributed Virtual Port Group of a VM (only single NIC supported)

    vm_name
        The name of the VM to change

    dvswitch_name
        The name of the Distributed Virtual Switch that contains the desired Port Group

    dport_group_name
        The name of the Distributed Port Group for the VM

    service_instance
        (optional) The Service Instance from which to obtain managed object references.

    profile
        Profile to use (optional)

    CLI Example:

    .. code-block:: bash

        salt '*' vmware_vm.set_dvportgroup vm1 dvs2 dport1 profile=vcsa_config1
    """
    log.debug("Running vmware_vm.set_dvport")
    service_instance = service_instance or connect.get_service_instance(
        config=__opts__, profile=profile
    )

    dvs = utils_vmware._get_dvs(service_instance, dvswitch_name)
    if not dvs:
        return {
            "success": False, 
            "comment": "setting distributed virtual port failed",
            "error": "Specified Distributed Switch not found"
        }

    port_group = utils_vmware._get_dvs_portgroup(dvs=dvs, portgroup_name=dport_group_name)
    if not port_group:
        return {
            "success": False, 
            "comment": "setting distributed virtual port failed",
            "error": "Specifed Distributed Port Group not found"

        }

    vm = utils_common.get_mor_by_property(
                service_instance,
                vim.VirtualMachine,
                vm_name,
            )
    if not vm:
        return {
            "success": False, 
            "comment": "setting distributed virtual port failed",
            "error": "Specified VM  not found"
        }
    if vm.summary.runtime.powerState == "poweredOn":
        return {
            "success": False, 
            "comment": "setting distributed virtual port failed",
            "error": "VM must be powered off"
        }

    vm_reconfig_spec = vim.vm.ConfigSpec()
    nic_change_spec = vim.vm.device.VirtualDeviceSpec()
    nic_change_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
    nic = None

    nic_count = 0
    for device in vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualEthernetCard):
            nic_count += 1
        if nic_count > 1:
            return {
                "success": False, 
                "comment": "setting distributed virtual port failed",
                "error": "Only VMs with a single NIC supported"
            }
        if isinstance(device, vim.vm.device.VirtualVmxnet3):
            nic = device

    port_config_spec = vim.dvs.PortConnection()
    port_config_spec.portgroupKey = port_group.key
    port_config_spec.switchUuid = port_group.config.distributedVirtualSwitch.uuid
    nic.backing = vim.vm.device.VirtualEthernetCard.DistributedVirtualPortBackingInfo()
    nic.backing.port = port_config_spec        
        
    nic_change_spec.device = nic
    vm_reconfig_spec.deviceChange.append(nic_change_spec)

    try:
        utils_vm.update_vm(vm, vm_reconfig_spec)
        ret = True
    except Exception as err:
        ret = {
            "success": False, 
            "comment": "setting distributed virtual port failed",
            "error": f"error updating Distributed Virtual Port Group: {err}"
        }

    return ret

