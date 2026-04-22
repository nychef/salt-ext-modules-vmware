# Salt Extension Modules for VMware

This is a collection of us-maintained extension modules for use with VMware
vSphere, vCenter, ESXi, and friends.

## Building the module

At the current time you'll need to build this module to install it. Please ensure to create a tag and then push the tag so that the version number is incremented.
```
git tag --list
git tag -a <tag-name+increment> -m "<message>"
git push origin <tag-name>
```
## Configuring a minion
The minion needs to have the profiles defined in its pillar in order to use this module.
Something like:
```
saltext.vmware:
  vdi-ny:
    host: vdi-ny-vcsa1.vdi.rentec.com
    user: administrator@vsphere.local
    password: |
        -----BEGIN PGP MESSAGE-----
        pgp encrypted password
        -----END PGP MESSAGE-----
```
## Executing code
Most of the functions have documentation. Poke around and see what is there.

