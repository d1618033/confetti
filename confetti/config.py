import copy
from sentinels import NOTHING
from . import exceptions
from .ref import Ref
from .python3_compat import iteritems

class Config(object):
    _backups = None
    def __init__(self, value=None, parent=None, metadata=None):
        super(Config, self).__init__()
        self._value = self._init_value(value)
        if isinstance(self._value, dict):
            self._fix_dictionary_value()
        self._parent = parent
        self.metadata = metadata
        self.root = ConfigProxy(self)
    def get_value(self):
        if self.is_leaf():
            return self._value
        raise NotImplementedError("Cannot get value of config object") # pragma: no cover
    def _init_value(self, value):
        if value is None:
            value = {}
        elif isinstance(value, dict):
            value = value.copy()
        return value
    def _fix_dictionary_value(self):
        to_replace = []
        for k, v in iteritems(self._value):
            if isinstance(v, dict):
                to_replace.append((k, Config(v, parent=self)))
        for k, v in to_replace:
            self._value[k] = v
    def is_leaf(self):
        return not isinstance(self._value, dict)
    def traverse_leaves(self):
        for key in self.keys():
            value = self.get_config(key)
            if value.is_leaf():
                yield key, value
            else:
                for subpath, cfg in value.traverse_leaves():
                    yield "{0}.{1}".format(key, subpath), cfg
    def __getitem__(self, item):
        returned = self._value[item]
        if isinstance(returned, Config) and returned.is_leaf():
            returned = returned._value
        if isinstance(returned, Ref):
            returned = returned.resolve(self)
        assert not isinstance(returned, dict)
        return returned
    def __contains__(self, key):
        return self.get(key, NOTHING) is not NOTHING
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
    def get_config(self, key):
        returned = self._value[key]
        if not isinstance(returned, Config):
            returned = Config(returned, parent=self)
        return returned
    def pop(self, key):
        return self._value.pop(key)
    def __setitem__(self, item, value):
        if not self._can_set_item(item, value):
            raise exceptions.CannotSetValue("Cannot set key {0!r}".format(item))
        self._value[item] = value
    def _can_set_item(self, item, value):
        return item in self._value or isinstance(value, Config)
    def keys(self):
        return self._value.keys()
    @classmethod
    def from_filename(cls, filename, namespace=None):
        with open(filename, "rb") as f:
            return cls.from_file(f, filename)
    @classmethod
    def from_file(cls, f, filename="?", namespace=None):
        ns = dict(__file__ = filename)
        if namespace is not None:
            ns.update(namespace)
        return cls.from_string(f.read(), namespace=namespace)
    @classmethod
    def from_string(cls, s, namespace = None):
        if namespace is None:
            namespace = {}
        else:
            namespace = dict(namespace)
        exec(s, namespace)
        return cls(namespace['CONFIG'])
    def backup(self):
        if self._backups is None:
            self._backups = []
        self._backups.append(_get_state(self))
    def restore(self):
        if not self._backups:
            raise exceptions.NoBackup()
        _set_state(self, self._backups.pop())
    def serialize_to_dict(self):
        return _get_state(self)
    def get_parent(self):
        return self._parent

class ConfigProxy(object):
    def __init__(self, conf):
        super(ConfigProxy, self).__init__()
        self._conf = conf
    def __dir__(self):
        return list(self._conf.keys())
    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return super(ConfigProxy, self).__setattr__(attr, value)
        assert isinstance(self._conf, Config)
        try:
            self._conf[attr] = value
        except exceptions.CannotSetValue:
            raise AttributeError(attr)
    def __getattr__(self, attr):
        value = self._conf[attr]
        if isinstance(value, dict):
            value = Config(value)
        if isinstance(value, Config):
            return ConfigProxy(value)
        return value

def _get_state(config):
    if isinstance(config, Config):
        if config.is_leaf():
            return config
        return _get_state(config._value)
    if isinstance(config, dict):
        returned = {}
        for key in config.keys():
            returned[key] = _get_state(config[key])
        return returned
    return config

def _set_state(config, state):
    assert isinstance(config, Config)
    for key in set(config.keys()) - set(state):
        config.pop(key)
    for key, value in iteritems(state):
        if isinstance(value, dict):
            _set_state(config[key], value)
        else:
            config[key] = value
