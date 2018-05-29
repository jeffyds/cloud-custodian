# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import six

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry
from c7n.manager import ResourceManager
from c7n.query import sources
from c7n.utils import local_session


class ResourceQuery(object):

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def filter(self, resource_manager, **params):
        m = resource_manager.resource_type
        enum_op, list_op, extra_args = m.enum_spec

        if extra_args:
            params.update(extra_args)

        op = getattr(getattr(resource_manager.get_client(), enum_op), list_op)
        data = [r.serialize(True) for r in op(**params)]

        return data

    @staticmethod
    def resolve(resource_type):
        if not isinstance(resource_type, type):
            raise ValueError(resource_type)
        else:
            m = resource_type
        return m


@sources.register('describe-azure')
class DescribeSource(object):

    def __init__(self, manager):
        self.manager = manager
        self.query = ResourceQuery(manager.session_factory)

    def get_resources(self, query):
        return self.query.filter(self.manager)

    def get_permissions(self):
        return ()

    def augment(self, resources):
        return resources


class QueryMeta(type):
    """metaclass to have consistent action/filter registry for new resources."""
    def __new__(cls, name, parents, attrs):
        if 'filter_registry' not in attrs:
            attrs['filter_registry'] = FilterRegistry(
                '%s.filters' % name.lower())
        if 'action_registry' not in attrs:
            attrs['action_registry'] = ActionRegistry(
                '%s.actions' % name.lower())

        return super(QueryMeta, cls).__new__(cls, name, parents, attrs)


@six.add_metaclass(QueryMeta)
class QueryResourceManager(ResourceManager):

    def __init__(self, data, options):
        super(QueryResourceManager, self).__init__(data, options)
        self.source = self.get_source(self.source_type)

    def augment(self, resources):
        return resources

    def get_permissions(self):
        return ()

    def get_source(self, source_type):
        return sources.get(source_type)(self)

    def get_client(self, service=None):
        if not service:
            return local_session(self.session_factory).client(
                "%s.%s" % (self.resource_type.service, self.resource_type.client))
        return local_session(self.session_factory).client(service)

    def get_cache_key(self, query):
        return {'source_type': self.source_type, 'query': query}

    @classmethod
    def get_model(cls):
        return ResourceQuery.resolve(cls.resource_type)

    @property
    def source_type(self):
        return self.data.get('source', 'describe-azure')

    def resources(self, query=None):
        key = self.get_cache_key(query)
        resources = self.augment(self.source.get_resources(query))
        self._cache.save(key, resources)
        return self.filter_resources(resources)

    def get_resources(self, resource_ids, **params):
        resource_client = self.get_client()
        m = self.resource_type
        get_client, get_op, extra_args = m.get_spec

        if extra_args:
            params.update(extra_args)

        op = getattr(getattr(resource_client, get_client), get_op)
        data = [
            op(rid, **params)
            for rid in resource_ids
        ]
        return [r.serialize(True) for r in data]
