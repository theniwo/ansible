# Vserver Management

This repositiory contains scripts for managing web servers via ansible

# Roles
Current roles are

* Deploy
  * docker
  * podman
  * apache
* Patch Management
  * patchall - patch systems with only security updates
  * checkservices - check if all services are up and running
* User Management
  * addpubkeys - deploy our public ssh keys

# Deploy
Deploy a server with basic packages, some settings, an admin user and an ssh config
*TODO: add admin user and ssh config*

```
ansible-playbook deploy.yml -i inventory -t deploy
```

# Patch Management


## Patching manually
If manual patching has to be done, the following command can be used:

```
ansible-playbook patchall.yml -i inventory

```

## Checking services manually
If you want to check running services manually, use this command:

```
ansible-playbook patchall.yml -i inventory -t checkservices
ansible-playbook patchall.yml -i inventory -t checkservices -l GROUP
ansible-playbook patchall.yml -i inventory -t checkservices -l HOSTNAME

```



# User Management

## Pubkey Management

Add or remove a pubkey in this file:
`roles/user_mgmt/files/pubkeys/keys.yml`

To deploy all public ssh keys use the following command:
```
ansible-playbook addpubkeys.yml -i inventory
```

# TODO
## refactor code
 - [ ] apache
 - [ ] checkservices
 - [ ] checkupdates
 - [ ] cron
 - [ ] deploy
 - [ ] docker
 - [ ] locale
 - [ ] mail
 - [ ] patchmanagement
 - [ ] podman
 - [ ] podman.bak
 - [ ] scripts
 - [ ] sshd
 - [ ] storagebox
 - [ ] swap
 - [ ] test
 - [ ] unattended-upgrades
 - [ ] user
 - [ ] user_mgmt

 ## Final Check
 - [ ] Ubuntu 20.04
 - [ ] Ubuntu 22.04
 - [ ] Ubuntu 24.04
 - [ ] Fedora 39
 - [ ] Fedora 40
 - [ ] Fedora 41
