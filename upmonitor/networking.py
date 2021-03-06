import time
import logging
import msgpack
import asyncore
import traceback

from . import utils

__all__ = ['Handler', 'run']

class CannotConnect(Exception):
    pass
class ConnectionRefused(Exception):
    pass
class NoDataReceived(Exception):
    pass

class _MethodCaller:
    __slots__ = ('_handler',)
    def __init__(self, handler):
        self._handler = handler
    def __getattr__(self, name):
        def method(**kwargs):
            kwargs['command'] = name
            kwargs = {key: (list(value) if isinstance(value, set) else value)
                      for (key, value) in kwargs.items()}
            self._handler.send(msgpack.packb(kwargs))
        return method


class Handler(asyncore.dispatcher_with_send):
    """Abstract class for managing a connection an events."""

    __slots__ = ('_plugins', '_unpacker', 'call')

    def __init__(self, sock=None, plugins=None):
        super(Handler, self).__init__(sock)
        if plugins is None:
            plugins = []
        self._plugins = plugins
        self._unpacker = msgpack.Unpacker(use_list=True, encoding='utf8')
        self.call = _MethodCaller(self)

    def readable(self):
        return True

    def writeable(self):
        return True

    def handle_read(self):
        data = self.recv(4096)
        self._unpacker.feed(data)
        while self._read_object():
            pass

    def _read_object(self):
        """Read an object and dispatch it according to the `command` entry."""
        try:
            obj = self._unpacker.unpack()
        except msgpack.exceptions.OutOfData:
            return False
        if obj is None:
            return False
        assert isinstance(obj, dict), obj
        assert 'command' in obj, obj
        assert isinstance(obj['command'], str), obj['command']
        command = obj.pop('command')
        self.call_plugins_pre_callback(command, obj)
        if hasattr(self, 'on_' + command):
            method = getattr(self, 'on_' + command)
            method(**obj)
        else:
            logging.info('Unknown command received: %s' % obj['command'])
        return True

    def call_plugins_pre_callback(self, command, kwargs):
        """Calls all plugins' callback associated with a given command
        (pre_XXX where XXX is the name of the command).

        :param command: The command name.
        :param kwargs: Parameters given with the command."""
        for plugin in self._plugins:
            if hasattr(plugin, 'pre_' + command):
                getattr(plugin, 'pre_' + command)(**kwargs)

    def call_plugins_post_callback(self, command, kwargs):
        """Calls all plugins' callback associated with a given command
        (post_XXX where XXX is the name of the command).

        :param command: The command name.
        :param kwargs: Parameters given with the command."""
        for plugin in self._plugins:
            if hasattr(plugin, 'post_' + command):
                getattr(plugin, 'post_' + command)(**kwargs)

    def handle_error(self):
        traceback.print_exc()


def run():
    """Run the network drivers."""
    try:
        while True:
            if utils.scheduler.empty():
                asyncore.loop(1.0, count=1)
            else:
                utils.scheduler.run()
    except KeyboardInterrupt:
        print('Received Ctrl-C. Exiting.')
        return
