from .connection import SpecProtocol
from . import config
import asyncio

try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

class Client:

    def __init__(self, host=None, port=None, loop=None):
        try:
            self.loop = asyncio.get_event_loop()
        except:
            self.loop = loop
        if not host:
            host = config.get('server', '127.0.0.1')
        if not port:
            port = config.get('port', 6510)
        coro = self.loop.create_connection(lambda: SpecProtocol(self.loop), host, port)
        try:
            self.transport, self.protocol = self.loop.run_until_complete(coro)
        except RuntimeError:
            fut = asyncio.ensure_future(coro())
            print(fut, type(fut))
            asyncio.ensure_future(self._connect_async(fut))
        self.total_time = None
        self.send_command("p \"SpecClient %s, Connected\"" % config.get('version'))

    @asyncio.coroutine
    def _connect_async(self, fut):
        transport, protocol = yield from fut
        self.transport = transport
        self.protocol = protocol

    def channel_read(self, property, callback=None):
        """
        Like self.get_data, but with a callback instead of async

        Args:
            property: isinstance(str) - Spec string property, e.g. 'var/A'
            callback: isinstance(callable) - can be asynchronous or not, will be executed once when specc server sends
            reply.
        Returns:
            None
        """
        self.protocol.send_msg_chan_read(property, callback=callback)
        
    @asyncio.coroutine
    def get_data(self, property):
        """
        Asynchronous helper function to get single property from Spec Server.

        Args:
            property: isinstance(str) - Spec string property, e.g. 'var/A'

        Returns:
            np.ndarray
        """
        fut = asyncio.Future()

        def callback(reply):
            if not fut.cancelled():
                fut.set_result(reply.data)

        self.protocol.send_msg_chan_read(property, callback=callback)
        result = yield from fut
        return result

    def register_channel(self, channel, callback=None):
        """
        Helper function to subscribe to a property of a Spec Server and assign a callback function.
        Args:
            channel: isinstance(str) - Property string to subsribe to, e.g. 'var/S'  or 'motor/th/position'.
            callback: isinstance(callable) - can be asynchronous or not, will be executed when specc server sends an
             update packet.

        Returns:
            None
        """
        self.protocol.registerChannel(channel, register=True, recieverSlot=callback)

    def send_command(self, cmd):
        """
        Fire and forget function for sending a command string to the Spec server. Commands will be added to the server's
        internal command loop and will be executed in order of arrival at the Spec server.

        Args:
            cmd: isinstance(str) - command string for Spec, i.e. anything you can write on the Spec command line.

        Returns:
            None
        """
        self.protocol.send_msg_cmd(cmd)
