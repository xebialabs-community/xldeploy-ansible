#!/usr/bin/python
# -*- coding: utf-8 -*-

import itertools
import base64
import ssl
import xml.etree.ElementTree as ET
from xml.dom.minidom import Document

from ansible.module_utils.basic import *

# python 2 workaround
try:
    from http.client import HTTPConnection, HTTPSConnection
    from urllib.parse import urlparse
except ImportError:
    from httplib import HTTPConnection, HTTPSConnection
    from urlparse import urlparse

class XLDeployCommunicator:
    """ XL Deploy Communicator using http & XML"""

    # TODO Manage 'context'

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
        return self.do_it("GET", path, "")

    def do_put(self, path, doc):
        return self.do_it("PUT", path, doc)

    def do_post(self, path, doc):
        return self.do_it("POST", path, doc)

    def do_delete(self, path):
        return self.do_it("DELETE", path, "", False)

    def do_it(self, verb, path, doc, parse_response=True):
        # print "DO {} {} on {} ".format(verb, path, self.endpoint)

        ssl_context = None
        if not self.validate_certs:
            ssl_context = ssl._create_unverified_context()

        parsed_url = urlparse(self.endpoint)
        if parsed_url.scheme == "https":
            conn = HTTPSConnection(
                parsed_url.hostname, parsed_url.port, context=ssl_context)
        else:
            conn = HTTPConnection(parsed_url.hostname, parsed_url.port)

        try:
            auth = base64.encodestring(('{}:{}'.format(self.username,
                                                  self.password)).encode()).decode().replace('\n', '')
            headers = {
                "Content-type": "application/xml",
                "Accept": "application/xml",
                "Authorization": "Basic {}".format(auth)
            }

            conn.request(verb, "/deployit/{}".format(path), doc, headers)
            response = conn.getresponse()
            # print response.status, response.reason
            if response.status != 200 and response.status != 204:
                raise Exception(
                    "Error when requesting XL Deploy Server [{}]:{}".format(response.status, response.reason))

            if parse_response:
                xml = ET.fromstring(response.read().decode())
                return xml

            return None
        finally:
            conn.close()

    def property_descriptors(self, typename):
        doc = self.do_get("metadata/type/{}".format(typename))
        return dict((pd.attrib['name'], pd.attrib['kind'])
                    for pd in doc.getiterator('property-descriptor'))

    def __str__(self):
        return "[endpoint={}, username={}]".format(self.endpoint, self.username)


class RepositoryService:
    """ Access to the repository REST service"""

    def __init__(self, communicator=None):
        self.communicator = communicator

    def read(self, id):
        doc = self.communicator.do_get('repository/ci/{}'.format(id))
        return ConfigurationItem.from_xlm(doc, self.communicator)

    def exists(self, id):
        doc = self.communicator.do_get('repository/exists/{}'.format(id))
        return "true" in doc.text

    def update(self, ci):
        doc = ConfigurationItem.to_xml(ci, self.communicator)
        updated = self.communicator.do_put('repository/ci/{}'.format(ci.id), doc)
        return ConfigurationItem.from_xlm(updated, self.communicator)

    def create(self, ci):
        doc = ConfigurationItem.to_xml(ci, self.communicator)
        updated = self.communicator.do_post('repository/ci/{}'.format(ci.id), doc)
        return ConfigurationItem.from_xlm(updated, self.communicator)

    def delete(self, id):
        self.communicator.do_delete("repository/ci/{}".format(id))


class ConfigurationItem:
    """ an XL Deploy Configuration item"""

    def __init__(self, type, id, properties):
        self.id = id
        self.type = type
        self.properties = properties

    def __str__(self):
        return "{} {} {}".format(
            self.id, self.type,
            dict(
                map(lambda t: (t[0], "********") if t[0] == "password" else t,
                    self.properties.items())))

    def __eq__(self, other):
        return self.id == other.id and self.type == other.type and self.properties == other.properties

    def __contains__(self, item):
        print("###################################################### {} ".format(item))
        # TODO: use DictDiffer https://github.com/hughdbrown/dictdiffer/blob/master/dictdiffer/__init__.py
        # TODO: manage Password

        if not self.id == item.id:
            return False
        if not self.type == item.type:
            return False
        # if not len(self.properties) == len(item.properties):
        #    return False

        for k, v in item.properties.items():
            if k not in self.properties:
                return False

            # python 2 workaround
            try:
                if type(self.properties[k]) is itertools.imap:
                    self.properties[k] = list(self.properties[k])
            except AttributeError:
                pass

            if type(self.properties[k]) is str:
                if not str(self.properties[k]) == str(v):
                    return False
            elif type(self.properties[k]) is list:
                if not set(v).issubset(set(self.properties[k])):
                    return False
            elif type(self.properties[k]) is dict:
                for item_k, item_v in v.items():
                    if item_k not in self.properties[k].keys() or str(
                            self.properties[k][item_k]) != str(item_v):
                        return False
        return True

    def properties(self):
        return self.properties

    def update_with(self, other):
        for k, v in other.properties.items():
            if k in self.properties:
                if isinstance(self.properties[k], list):
                    self.properties[k] = list(set(self.properties[k] + v))
                elif isinstance(self.properties[k], dict):
                    self.properties[k].update(v)
                else:
                    self.properties[k] = v
            else:
                self.properties[k] = v

    @staticmethod
    def from_xlm(doc, communicator):
        descriptors = communicator.property_descriptors(doc.tag)

        def collection_of_string(xml):
            return map(lambda e: e.text, xml)

        def collection_of_ci(xml):
            return map(lambda e: e.attrib['ref'], xml)

        def map_string_string(xml):
            return dict((child.attrib['key'], child.text) for child in xml)

        def ci(xml):
            return xml.attrib['ref']

        def default(xml):
            return xml.text

        properties = dict((xml.tag, {
            'SET_OF_STRING': collection_of_string,
            'LIST_OF_STRING': collection_of_string,
            'SET_OF_CI': collection_of_ci,
            'LIST_OF_CI': collection_of_ci,
            'MAP_STRING_STRING': map_string_string,
            'CI': ci
        }.get(descriptors[xml.tag], default)(xml)) for xml in doc)

        return ConfigurationItem(doc.tag, doc.attrib['id'], properties)

    @staticmethod
    def to_xml(item, communicator):
        descriptors = communicator.property_descriptors(item.type)
        doc = Document()
        base = doc.createElement(item.type)
        base.attributes['id'] = item.id
        doc.appendChild(base)

        def collection_of_string(doc, key, value):
            node = doc.createElement(key)
            for s in value:
                value = doc.createElement('value')
                value.appendChild(doc.createTextNode(s))
                node.appendChild(value)
            return node

        def collection_of_ci(doc, key, value):
            node = doc.createElement(key)
            for ci in value:
                cinode = doc.createElement('ci')
                cinode.attributes['ref'] = ci
                node.appendChild(cinode)
            return node

        def map_string_string(doc, key, value):
            node = doc.createElement(key)
            for k, v in value.items():
                entry = doc.createElement('entry')
                entry.attributes['key'] = k
                entry.appendChild(doc.createTextNode(v))
                node.appendChild(entry)
            return node

        def ci(doc, key, value):
            node = doc.createElement(key)
            node.attributes['ref'] = value
            return node

        def default(doc, key, value):
            node = doc.createElement(key)
            node.appendChild(doc.createTextNode(str(value)))
            return node

        for key, value in item.properties.items():
            if not key in descriptors:
                raise Exception("'{}' is not a property of '{}'".format(key,
                                                                    item.type))

            base.appendChild({
                'SET_OF_STRING': collection_of_string,
                'LIST_OF_STRING': collection_of_string,
                'SET_OF_CI': collection_of_ci,
                'LIST_OF_CI': collection_of_ci,
                'MAP_STRING_STRING': map_string_string,
                'CI': ci
            }.get(descriptors[key], default)(doc, key, value))

        return doc.toxml()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            username=dict(default='admin'),
            password=dict(default='admin', no_log=True),
            endpoint=dict(default='http://localhost:4516'),
            validate_certs=dict(required=False, type='bool', default=True),
            id=dict(),
            type=dict(),
            properties=dict(type='dict', default={}),
            state=dict(default='present', choices=['present', 'absent']),
            update_mode=dict(default='replace', choices=['add', 'replace']),
        ))

    communicator = XLDeployCommunicator(
        module.params.get('endpoint'), module.params.get('username'),
        module.params.get('password'), module.params.get('validate_certs'),
        module.params.get('context'))

    repository = RepositoryService(communicator)
    ci_id = module.params.get('id')
    ci = ConfigurationItem(
        module.params.get('type'), ci_id, module.params.get('properties'))

    msg = ""
    try:
        state = module.params.get('state')
        if state == 'absent':
            msg = "Delete {}".format(ci)
            repository.delete(ci.id)
        elif state == 'present':
            if repository.exists(ci_id):
                existing_ci = repository.read(ci_id)
                update_mode = module.params.get('update_mode')
                if update_mode == 'replace':
                    msg = "[REPLACE] Update {}, previous {}".format(
                        ci, existing_ci)
                    repository.update(ci)
                else:
                    if ci in existing_ci:
                        module.exit_json(changed=False)
                    else:
                        msg = "[ADD] Update {}, previous {}".format(ci,
                                                                existing_ci)
                    existing_ci.update_with(ci)
                    repository.update(existing_ci)
            else:
                msg = "Create {}".format(ci)
                repository.create(ci)

        module.exit_json(changed=True, msg=msg)
    except Exception as e:
        # exc_type, exc_value, exc_traceback = sys.exc_info()
        module.fail_json(
            msg="Failed to update XLD {} on {}, about ci [{}]:  {}".format(
                e, communicator, ci, traceback.format_exc()))


main()
