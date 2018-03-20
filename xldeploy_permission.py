#!/usr/bin/python
# -*- coding: utf-8 -*-

ANSIBLE_METADATA = {
    'metadata_version': '1.0',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: xldeploy_permission

short_description: Module to add XLDeploy from Xebialabs Persmissions through its API

version_added: "2.4"

description:
    - "The module uses the API described under https://docs.xebialabs.com/xl-deploy/7.6.x/rest-api/com.xebialabs.deployit.engine.api.PermissionService.html"
    - "It uses PUT to Grants Permissions with /security/permission/{permission}/{role}/{id:.*}"
    - "It uses DELETE to Revoke Permissions with /security/permission/{permission}/{role}/{id:.+}"
    - "It uses GET to maintain the idempotency and checks the current status with /security/permission/{permission}/{role}/{id:.+}"

options:
    id:
        description:
            - The path of the CI to grant/revoke the permission on.
        required: true
    role:
        description:
            - The role to which the permission should be granted/revoked.
        required: true
    permission:
        description:
            - The name of the permission to grant/revoke.
        required: true
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
        default: grant

extends_documentation_fragment:
    - xldeploy

author:
    - RAET (@imjoseangel)
'''

EXAMPLES = '''
# Revoke a read Permission for admins under Environments/DEV/ANSIBLE
- name: Revoke Permissions
    xldeploy_permission:
    id: Environments/DEV/ANSIBLE
    role: admins
    permission: read
    endpoint: http://localhost:4516
    username: admin
    password: password
    validate_certs: False
    state: revoke

# Grant read permission for admins under Environments/DEV/ANSIBLE
- name: Grant Permissions
    xldeploy_permission:
    id: Environments/DEV/ANSIBLE
    role: admins
    permission: read
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
    sample: "Already Revoked [permission] for role *role* on *id*"
'''

import itertools
import base64
import httplib
from urllib2 import quote
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
                return xml.text

            return None
        finally:
            conn.close()

    def __str__(self):
        return "[endpoint=%s, username=%s]" % (self.endpoint, self.username)


class PermissionService:
    """ Access to the permission REST service"""

    def __init__(self, communicator=None):
        self.communicator = communicator

    def read(self, id):
        doc = self.communicator.do_get('security/permission/%s' % id)
        return "true" in doc

    def grant(self, id):
        self.communicator.do_put('security/permission/%s' % id)

    def revoke(self, id):
        self.communicator.do_delete("security/permission/%s" % id)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            username=dict(default='admin'),
            password=dict(default='admin', no_log=True),
            endpoint=dict(default='http://localhost:4516'),
            validate_certs=dict(required=False, type='bool', default=True),
            id=dict(type='str', required=True),
            role=dict(type='str', required=True),
            permission=dict(type='str', required=True),
            state=dict(default='grant', choices=['revoke', 'grant'])))

    communicator = XLDeployCommunicator(
        module.params.get('endpoint'), module.params.get('username'),
        module.params.get('password'), module.params.get('validate_certs'),
        module.params.get('context'))

    repository = PermissionService(communicator)
    sec_id = module.params.get('id')
    sec_role = module.params.get('role')
    sec_perm = module.params.get('permission')
    sec = "%s/%s/%s" % (quote(sec_perm), sec_role, sec_id)

    msg = ""
    try:
        state = module.params.get('state')
        if state == 'revoke':
            existing_sec = repository.read(sec)
            if existing_sec == True:
                msg = "Revoking [%s] for role %s on %s" % (sec_perm, sec_role,
                                                           sec_id)
                repository.revoke(sec)
                module.exit_json(changed=True, msg=msg)
            else:
                msg = "Already Revoked [%s] for role %s on %s" % (sec_perm,
                                                                  sec_role,
                                                                  sec_id)
                module.exit_json(changed=False, msg=msg)
        elif state == 'grant':
            existing_sec = repository.read(sec)
            if existing_sec == False:
                msg = "Granting [%s] for role %s on %s" % (sec_perm, sec_role,
                                                           sec_id)
                repository.grant(sec)
                module.exit_json(changed=True, msg=msg)
            else:
                msg = "Already Granted [%s] for role %s on %s" % (sec_perm,
                                                                  sec_role,
                                                                  sec_id)
                module.exit_json(changed=False, msg=msg)
        else:
            module.exit_json(changed=False)
    except Exception as e:
        module.fail_json(
            msg="Failed to update XLD %s on %s, about sec [%s]:  %s" % (
                e, communicator, sec, traceback.format_exc()))


main()
