# ansible
Ansible Playbooks for various stuff

## vserver
Ansible playbooks for vserver

Ensure to have an `invetories/inventory` file with the following content:

```
[all:vars]
ansible_user='root'
ansible_become=yes
ansible_become_method=sudo
ansible_python_interpreter=/usr/bin/python3

[all]

[init]

[deploy]

[patch]

[keys]

[docker_server]

```
