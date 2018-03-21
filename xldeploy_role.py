#!/usr/bin/python
# -*- coding: utf-8 -*-

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: xldeploy_role

short_description: Module to add XLDeploy from Xebialabs Roles and Principals through its API

version_added: "2.4"

description:
    - "The module uses the API described under https://docs.xebialabs.com/generated/xl-deploy/7.6.x/rest-api/com.xebialabs.deployit.engine.api.RoleService.html"
    - "It uses PUT to Grants Permissions with /security/role/{role}/{principal} or /security/role/{role}"
    - "It uses DELETE to Revoke Permissions with /security/role/{role}/{principal} or /security/role/{role}"
    - "It uses GET to maintain the idempotency and checks the current status with /security/role/ or /security/role/roles/{username}"

options:
    role:
        description:
            - The role to be created/deleted
        required: true
    principal:
        description:
            - The name of the user or group  to assign/remove the role to
        required: false
    endpoint:
        description:
            - The name of the enpoint
        required: false
        default: http://localhost:4516
    username:
        description:
            - The name of the user for the endpoint
        required: false
        default: admin
    password:
        description:
            - The password of the user for the endpoint
        required: false
        default: admin
    validate_certs:
        description:
            - SSL/TLS Certificate Validation Flag
        required: false
        default: true
    state:
        description:
            - Action to Commit
        required: false
        default: present

extends_documentation_fragment:
    - xldeploy

author:
    - RAET (@imjoseangel)
'''

EXAMPLES = '''
# Remove myotheradmin from admins role
- name: Create Rol / Principal
    xldeploy_role:
      role: admins
      principal: myotheradmin
      endpoint: http://localhost:4516
      username: admin
      password: password
      validate_certs: False
      state: absent

# Remove ansible role
- name: Create Rol / Principal
    xldeploy_role:
      role: ansible
      endpoint: http://localhost:4516
      username: admin
      password: password
      validate_certs: False
      state: absent

# Add admin principal to admins role (Role is created if it doesn't exist)
- name: Grant Permissions
    xldeploy_role:
      role: admins
      principal: admin
      endpoint: http://localhost:4516
      username: admin
      password: password
      validate_certs: False

# Add admins role only (No Principals associated)
- name: Grant Permissions
    xldeploy_role:
      role: admins
      endpoint: http://localhost:4516
      username: admin
      password: password
      validate_certs: False
'''

RETURN = '''
msg:
    description: The operation done after confirming current status
    type: str
    returned: always
    sample: "Role [role] already present for principal *principal*"
'''

import itertools
import base64
import httplib
import ssl
from urlparse import urlparse
import xml.etree.ElementTree as ET
from xml.dom.minidom import Document

from ansible.module_utils.basic import *


class XLDeployCommunicator:
    """ XL Deploy Communicator using http & XML"""

    def __init__(self,
                 endpoint='http://localhost:4516',
                 username='admin',
                 password='admin',
                 validate_certs=True,
                 context='deployit'):
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.validate_certs = validate_certs
        self.context = context

    def do_get(self, path):
        return self.do_it("GET", path, True)

    def do_put(self, path):
        return self.do_it("PUT", path, False)

    def do_delete(self, path):
        return self.do_it("DELETE", path, False)

    def do_it(self, verb, path, parse_response=True):

        ssl_context = None
        if not self.validate_certs:
            ssl_context = ssl._create_unverified_context()

        parsed_url = urlparse(self.endpoint)
        if parsed_url.scheme == "https":
            conn = httplib.HTTPSConnection(
                parsed_url.hostname, parsed_url.port, context=ssl_context)
        else:
            conn = httplib.HTTPConnection(parsed_url.hostname, parsed_url.port)

        try:
            auth = base64.encodestring('%s:%s' % (self.username,
                                                  self.password)).replace(
                                                      '\n', '')
            headers = {
                "Content-type": "application/xml",
                "Accept": "application/xml",
                "Authorization": "Basic %s" % auth
            }

            conn.request(verb, "/deployit/%s" % path, headers=headers)
            response = conn.getresponse()

            # print response.status, response.reason, response.read()
            if response.status != 200 and response.status != 204:
                raise Exception(
                    "Error when requesting XL Deploy Server [%s]:%s" %
                    (response.status, response.reason))

            if parse_response:
                xml = ET.fromstring(str(response.read()))
                xmlchild = xml.getchildren()
                children = []
                for content in xmlchild:
                    children.append(content.text)
                return children

            return None
        finally:
            conn.close()

    def __str__(self):
        return "[endpoint=%s, username=%s]" % (self.endpoint, self.username)


class RoleService:
    """ Access to the role REST service"""

    def __init__(self, communicator=None):
        self.communicator = communicator

    def read(self, id):
        doc = self.communicator.do_get('security/role/%s' % id)
        return doc

    def create(self, id):
        self.communicator.do_put('security/role/%s' % id)

    def delete(self, id):
        self.communicator.do_delete("security/role/%s" % id)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            username=dict(default='admin'),
            password=dict(default='admin', no_log=True),
            endpoint=dict(default='http://localhost:4516'),
            validate_certs=dict(required=False, type='bool', default=True),
            role=dict(type='str', required=True),
            principal=dict(type='str', required=False),
            state=dict(default='present', choices=['present', 'absent'])))

    communicator = XLDeployCommunicator(
        module.params.get('endpoint'), module.params.get('username'),
        module.params.get('password'), module.params.get('validate_certs'),
        module.params.get('context'))

    repository = RoleService(communicator)
    role = module.params.get('role')
    prin = module.params.get('principal')
    if prin is None:
        srvc_get = ""
        srvc = "%s" % (role)
    else:
        srvc_get = "roles/%s" % (prin)
        srvc = "%s/%s" % (role, prin)

    msg = ""

    try:
        state = module.params.get('state')
        if state == 'present':
            existing_item = repository.read(srvc_get)
            if prin is None:
                if role in existing_item:
                    msg = "Role [%s] already present" % (role)
                    module.exit_json(changed=False, msg=msg)
                else:
                    msg = "Creating role [%s]" % (role)
                    repository.create(srvc)
                    module.exit_json(changed=True, msg=msg)
            else:
                if role in existing_item:
                    msg = "Role [%s] already present for principal %s" % (
                        role, prin)
                    module.exit_json(changed=False, msg=msg)
                else:
                    msg = "Creating principal %s under role [%s]" % (
                        prin, role)
                    repository.create(srvc)
                    module.exit_json(changed=True, msg=msg)
        elif state == 'absent':
            existing_item = repository.read(srvc_get)
            if prin is None:
                if role in existing_item:
                    msg = "Deleting role [%s]" % (role)
                    repository.delete(srvc)
                    module.exit_json(changed=True, msg=msg)
                else:
                    msg = "Role [%s] already deleted" % (role)
                    module.exit_json(changed=False, msg=msg)
            else:
                if role in existing_item:
                    msg = "Deleting principal %s under role [%s]" % (
                        prin, role)
                    repository.delete(srvc)
                    module.exit_json(changed=True, msg=msg)
                else:
                    msg = "Role [%s] already delete for principal %s" % (
                        role, prin)
                    module.exit_json(changed=False, msg=msg)
        else:
            module.exit_json(changed=False)
    except Exception as e:
        module.fail_json(
            msg="Failed to update XLD %s on %s, about role [%s]:  %s" % (
                e, communicator, srvc, traceback.format_exc()))


if __name__ == '__main__':
    main()
