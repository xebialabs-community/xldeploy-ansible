Ansible Module for XL Deploy
================

This module allows you to use [Ansible](http://www.ansibleworks.com/) to manage the  [XLDeploy](http://www.xebialabs.com) repository

Usage Examples
==============

The module updates the XL Deploy repository by defining the containers managed by Ansible

The example below configure 3 containers in XL Deploy and add them to a brand new environment.
The example also adds security to the Environments/others folder with the module xldeploy_permission.

```yaml
- name: Configure Tomcat Server
  hosts: tomcatserver
  tasks:
    - name: define node in XLD
      xldeploy:
        id: Infrastructure/ansible.vm
        type: overthere.SshHost
        endpoint: http://10.0.2.2:4516
        username: xldeployuser
        password: MySuperS3cr3tPassw0rd
        validate_certs: False
        properties:
          os: UNIX
          address: "{{ ansible_default_ipv4.address }}"
          username: scott
          password: tiger
    - name : define tomcat server in XLD
      xldeploy:
        id: Infrastructure/ansible.vm/tomcat
        type: tomcat.Server
        endpoint: http://10.0.2.2:4516
        username: xldeployuser
        password: MySuperS3cr3tPassw0rd
        validate_certs: False
        properties:
          home: /opt/tomcat
          startCommand: /etc/init.d/tomcat start
          stopCommand: /etc/init.d/tomcat stop
          startWaitTime: 10
          stopWaitTime: 0
    - name : define tomcat virtual host in XLD
      xldeploy:
        id: Infrastructure/ansible.vm/tomcat/tomcat.vh
        type: tomcat.VirtualHost
        endpoint: http://10.0.2.2:4516
        username: xldeployuser
        password: MySuperS3cr3tPassw0rd
        validate_certs: False
    - name: add other environment folder
      xldeploy:
        id: Environments/others
        type: core.Directory
        endpoint: http://10.0.2.2:4516
        username: xldeployuser
        password: MySuperS3cr3tPassw0rd
        validate_certs: False
    - name: define test environment
      xldeploy:
        id: Environments/others/tomcat-test
        type: udm.Environment
        endpoint: http://10.0.2.2:4516
        username: xldeployuser
        password: MySuperS3cr3tPassw0rd
        validate_certs: False
        properties:
          members: [Infrastructure/ansible.vm/tomcat/tomcat.vh, Infrastructure/ansible.vm/tomcat, Infrastructure/ansible.vm ]
    - name: Add Permissions
      xldeploy_permission:
        id: Environments/others
        role: admins
        permission: "{{ item }}"
        endpoint: http://10.0.2.2:4516
        username: xldeployuser
        password: MySuperS3cr3tPassw0rd
        validate_certs: False
        state: grant
      with_items:
        - deploy#undeploy
        - deploy#initial
        - read
    - name: Create Role / Principal
      xldeploy_role:
        role: admins
        principal: "{{ item }}"
        endpoint: http://10.0.2.2:4516
        username: xldeployuser
        password: pasMySuperS3cr3tPassw0rdsword
        validate_certs: False
      with_items:
        - admin
        - ansible

```

A complete demo usage using Vagrant is available [here](https://github.com/xebialabs-community/xl-deploy-ansible-sample)
