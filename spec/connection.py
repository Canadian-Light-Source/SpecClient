from spec.message import *
from spec.message import message as spec_message
from spec.wait import *
from spec import config
import asyncio
import nest_asyncio

nest_asyncio.apply()
import datetime
import logging
import time
import weakref

try:
    import sgmdata
    import os
    from bokeh.io import output_notebook

    os.environ['JHUB_ADMIN'] = '1'
    os.environ['JUPYTERHUB_USER'] = 'arthurz'
    os.environ['DB_ENV_SECRET'] = config.get('db')
    PLOT_ENABLED = True
except:
    PLOT_ENABLED = False
    print("Running without plotting enabled")

logger = logging.getLogger("SpecClient")
logger.setLevel(logging.DEBUG)

(DISCONNECTED, PORTSCANNING, WAITINGFORHELLO, CONNECTED) = (1, 2, 3, 4)
(MIN_PORT, MAX_PORT) = (6510, 6530)
(DOREG, DONTREG, WAITREG) = (0, 1, 2)


class SpecChannel:
    """SpecChannel class
    Represent a channel in Spec
    Signals:
    valueChanged(channelValue, channelName) -- emitted when the channel gets updated
    """

    def __init__(self, connection, channelName, register=True):
        """Constructor
        Arguments:
        connection -- a SpecConnection object
        channelName -- string representing a channel name, i.e. 'var/toto'
        """
        self.loop = asyncio.get_event_loop()
        self.connection = weakref.ref(connection)
        self.name = channelName
        self.isUpdated = asyncio.Event()
        self.callback = None

        if channelName.startswith("var/") and "/" in channelName[4:]:
            l = channelName.split("/")
            self.spec_chan_name = "/".join((l[0], l[1]))

            if len(l) == 3:
                self.access1 = l[2]
                self.access2 = None
            else:
                self.access1 = l[2]
                self.access2 = l[3]
        else:
            self.spec_chan_name = self.name
            self.access1 = None
            self.access2 = None
        self.registrationFlag = DOREG if register else DONTREG
        self.isdisconnected = True
        self.registered = False
        self.value = None

        if not connection.on_con_lost.result():
            self.connected()

    def connected(self):
        """Do registration when Spec gets connected
        If registration flag is WAITREG put the flag to DOREG if not yet connected,
        and register if DOREG
        """
        if self.registrationFlag == WAITREG:
            if self.isdisconnected:
                self.registrationFlag = DOREG

        self.isdisconnected = False

        if self.registrationFlag == DOREG:
            if not self.registered:
                self.register()

    def disconnected(self):
        """Reset channel object when Spec gets disconnected."""
        self.value = None
        self.isdisconnected = True
        self.registered = False

    def unregister(self):
        """Unregister channel."""
        connection = self.connection()

        if not connection.on_con_lost.result():
            connection.send_msg_unregister(self.spec_chan_name)
            self.registered = False
            self.value = None

    def register(self):
        """Register channel
        Registering a channel means telling the server we want to receive
        update events when a channel value changes on the server side.
        """
        if self.spec_chan_name != self.name:
            return

        connection = self.connection()

        if not connection.on_con_lost.result():
            connection.send_msg_register(self.spec_chan_name)
            self.registered = True

    def _coerce(self, value):
        try:
            value = int(value)
        except BaseException:
            try:
                value = float(value)
            except BaseException:
                pass
        return value

    def update(self, channelValue, epoch=None, deleted=False, force=False):
        """Update channel's value and emit the 'valueChanged' signal."""
        if isinstance(channelValue, dict) and self.access1 is not None:
            if self.access1 in channelValue:
                if not deleted:
                    if self.access2 is None:
                        if (
                                force
                                or self.value is None
                                or self.value != channelValue[self.access1]
                        ):
                            if isinstance(channelValue[self.access1], dict):
                                self.value = channelValue[self.access1].copy()
                            else:
                                self.value = self._coerce(channelValue[self.access1])
                    else:
                        if self.access2 in channelValue[self.access1]:
                            if not deleted:
                                if (
                                        force
                                        or self.value is None
                                        or self.value
                                        != channelValue[self.access1][self.access2]
                                ):
                                    self.value = self._coerce(
                                        channelValue[self.access1][self.access2]
                                    )
                    if asyncio.iscoroutinefunction(self.callback):
                        self.loop.create_task(self.callback(self.name, channelValue, epoch=epoch))
                        data_name = "_".join(str(self.name).split('/'))

                    self.isUpdated.set()

            return

        if isinstance(self.value, dict) and isinstance(channelValue, dict):
            # update dictionary
            if deleted:
                for key, val in channelValue.items():
                    if isinstance(val, dict):
                        for k in val:
                            try:
                                del self.value[key][k]
                            except KeyError:
                                pass
                        if len(self.value[key]) == 1 and None in self.value[key]:
                            self.value[key] = self.value[key][None]
                    else:
                        try:
                            del self.value[key]
                        except KeyError:
                            pass
            else:
                for k1, v1 in channelValue.items():
                    if isinstance(v1, dict):
                        try:
                            self.value[k1].update(v1)
                        except KeyError:
                            self.value[k1] = v1
                        except AttributeError:
                            self.value[k1] = {None: self.value[k1]}
                            self.value[k1].update(v1)
                    else:
                        if k1 in self.value and isinstance(self.value[k1], dict):
                            self.value[k1][None] = v1
                        else:
                            self.value[k1] = v1
                if asyncio.iscoroutinefunction(self.callback):
                    self.loop.create_task(self.callback(self.name, channelValue, epoch=epoch))

                self.isUpdated.set()

        else:
            if deleted:
                self.value = None
            else:
                self.value = channelValue
                if asyncio.iscoroutinefunction(self.callback):
                    self.loop.create_task(self.callback(self.name, channelValue, epoch=epoch))

                self.isUpdated.set()

    def read(self, timeout=3, force_read=False):
        """Read the channel value
        If channel is registered, just return the internal value,
        else obtain the channel value and return it.
        """
        if not force_read and self.registered:
            if self.value is not None:
                # we check 'value is not None' because the
                # 'registered' flag could be set, but before
                # the message with the channel value arrived
                self.isUpdated = asyncio.Event()
                return self.value

        connection = self.connection()

        if not connection.on_con_lost.result():
            # make sure spec is connected, we give a short timeout
            # because it is supposed to be the case already
            value = waitReply(connection, "send_msg_chan_read", (self.spec_chan_name,))
            value = asyncio.ensure_future(value)

            if value is None:
                raise RuntimeError("could not read channel %r" % self.spec_chan_name)
            self.update(value)
            self.isUpdated = asyncio.Event()
            return self.value

    def write(self, value, wait=False):
        """Write a channel value."""
        connection = self.connection()

        if connection is not None:
            if self.access1 is not None:
                if self.access2 is None:
                    value = {self.access1: value}
                else:
                    value = {self.access1: {self.access2: value}}

            connection.send_msg_chan_send(self.spec_chan_name, value, wait)


class SpecProtocol(asyncio.Protocol):
    def __init__(self, loop):
        self.transport = None
        self.on_con_lost = loop.create_future()
        self.on_con_lost.set_result(False)
        self.registeredReplies = {}
        self.registeredChannels = {}
        self.state = None
        self.loop = loop
        self.serverVersionF = loop.create_future()
        self.serverVersion = 4
        self.name = 'SPEC'
        self.nameF = loop.create_future()
        self.socket_write_event = asyncio.Event()
        self.outgoing_queue = []
        self.buffer = []
        self._completed_writing_event = asyncio.Event()
        self.channel_name = None

    def connection_made(self, transport):
        self.state = WAITINGFORHELLO
        self.transport = transport
        self.send_msg_hello()

    def data_received(self, data):
        message = None
        self.buffer.append(data)

        s = b"".join(self.buffer)
        offset = 0
        while offset < len(s):
            if message is None:
                message = spec_message(version=self.serverVersion)

            try:
                consumedBytes = message.readFromStream(s[offset:])
            except Exception as e:
                print(f"MESSAGE ERROR: {e}")
                if len(self.buffer):
                    self.buffer = self.buffer[1:]
                else:
                    self.buffer = []
                break

            if consumedBytes == 0:
                break

            offset += consumedBytes

            if message.isComplete():
                try:
                    try:
                        # dispatch incoming message
                        if message.cmd == REPLY:
                            replyID = message.sn
                            if replyID > 0:
                                try:
                                    reply = self.registeredReplies[replyID]
                                    if hasattr(reply, 'callback'):
                                        if asyncio.iscoroutinefunction(reply.callback):
                                            self.loop.create_task(reply.callback(reply))
                                except BaseException:
                                    logging.getLogger("SpecClient").exception(
                                        "Unexpected error while receiving a message from server"
                                    )
                                else:
                                    del self.registeredReplies[replyID]
                                    reply.update(
                                        message.data, message.type == ERROR, message.err
                                    )

                        elif message.cmd == EVENT:
                            try:
                                channel = self.registeredChannels[message.name]
                            except KeyError:
                                pass
                            else:
                                second = float(str(message.sec) + "." + str(message.usec))
                                channel.update(message.data, second, message.flags == DELETED)
                        elif message.cmd == HELLO_REPLY:
                            self.serverVersion = message.vers
                            self.serverVersionF.set_result(self.serverVersion)
                            self.name = message.data.upper()
                            self.nameF.set_result(self.name)
                    except BaseException:
                        receivedStrings = [s[offset:]]
                        raise
                finally:
                    message = None
            self.buffer = [s[offset:]]

    def connection_lost(self, exc):
        # The socket has been closed
        self.on_con_lost.set_result(True)

    def send_msg_hello(self):
        """Send a hello message."""
        self.transport.write(msg_hello().sendingString())

    def send_msg_cmd_with_return(self, cmd, callback=None):
        """Send a command message to the remote Spec server,
           and return the reply id.
        Arguments:
        cmd -- command string, i.e. '1+1'
        """
        self.__send_msg_with_reply(
            replyCallback=callback,
            *msg_cmd_with_return(cmd, version=self.serverVersion)
        )

    def send_msg_func_with_return(self, cmd, callback=None):
        """Send a command message to the remote Spec server using the
           new 'func' feature, and return the reply id.
        Arguments:
        cmd -- command string
        """
        if self.serverVersion < 3:
            logging.getLogger("SpecClient").error(
                "Cannot execute command in Spec : feature is available since Spec server v3 only"
            )
        else:
            message = msg_func_with_return(cmd, version=self.serverVersion)
            self.__send_msg_with_reply(replyCallback=callback, *message)

    def send_msg_cmd(self, cmd):
        """Send a command message to the remote Spec server.
        Arguments:
        cmd -- command string, i.e. 'mv psvo 1.2'
        """
        self.__send_msg_no_reply(msg_cmd(cmd, version=self.serverVersion))

    def send_msg_func(self, cmd):
        """Send a command message to the remote Spec server using the new 'func' feature
        Arguments:
        cmd -- command string
        """
        if self.serverVersion.result() < 3:
            logging.getLogger("SpecClient").error(
                "Cannot execute command in Spec : feature is available since Spec server v3 only"
            )
        else:
            self.__send_msg_no_reply(msg_func(cmd, version=self.serverVersion))

    def send_msg_chan_read(self, chanName, callback=None):
        """Send a channel read message, and return the reply id.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        """
        return self.__send_msg_with_reply(
            replyCallback=callback, *msg_chan_read(chanName, version=self.serverVersion)
        )

    def send_msg_chan_send(self, chanName, value, wait=False):
        """Send a channel write message.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        value -- channel value
        """
        self.__send_msg_no_reply(
            msg_chan_send(chanName, value, version=self.serverVersion), wait
        )

    def send_msg_register(self, chanName):
        """Send a channel register message.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        """
        self.__send_msg_no_reply(msg_register(chanName, version=self.serverVersion))

    def send_msg_unregister(self, chanName):
        """Send a channel unregister message.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        """
        self.__send_msg_no_reply(msg_unregister(chanName, version=self.serverVersion))

    def send_msg_close(self):
        """Send a close message."""
        self.__send_msg_no_reply(msg_close(version=self.serverVersion))

    def send_msg_abort(self, wait=False):
        """Send an abort message."""
        self.__send_msg_no_reply(msg_abort(version=self.serverVersion), wait)

    def __send_msg_with_reply(self, reply, message, replyCallback=None):
        """Send a message to the remote Spec, and return the reply id.
        The reply object is added to the registeredReplies dictionary,
        with its reply id as the key. The reply id permits then to
        register for the reply using the 'registerReply' method.
        Arguments:
        reply -- SpecReply object which will receive the reply
        message -- SpecMessage object defining the message to send
        """
        replyID = reply.id
        self.registeredReplies[replyID] = reply

        if callable(replyCallback):
            reply.cmd = message.name
            reply.callback = replyCallback

        self.__send_msg_no_reply(message)

        return reply  # print "REPLY ID", replyID

    def __do_send_data(self):
        buffer = b"".join(self.outgoing_queue)
        if not buffer:
            self._completed_writing_event.set()
            return
        sent_bytes = self.transport.write(buffer)
        self.outgoing_queue = [buffer[sent_bytes:]]

    def __send_msg_no_reply(self, message, wait=False):
        """Send a message to the remote Spec.
        If a reply is sent depends only on the message, and not on the
        method to send the message. Using this method, any reply is
        lost.
        """
        if not self.socket_write_event.is_set():
            self.socket_write_event.set()
            self.transport.write(message.sendingString())
            self.socket_write_event.clear()

    def registerChannel(self, chanName, register=True, recieverSlot=None):
        """Register a channel
        Tell the remote Spec we are interested in receiving channel update events.
        If the channel is not already registered, create a new SpecChannel object,
        and connect the channel 'valueChanged' signal to the receiver slot. If the
        channel is already registered, simply add a connection to the receiver
        slot.
        Arguments:
        chanName -- a string representing the channel name, i.e. 'var/toto'
        receiverSlot -- any callable object in Python
        Keywords arguments:
        registrationFlag -- internal flag
        """
        chanName = str(chanName)

        try:
            if chanName not in self.registeredChannels:
                channel = SpecChannel(self, chanName, register)
                self.registeredChannels[chanName] = channel
                if channel.spec_chan_name != chanName:
                    self.registerChannel(channel.spec_chan_name, channel.update)
                channel.registered = True
            else:
                channel = self.registeredChannels[chanName]

            channel.callback = recieverSlot

            # channel.spec_chan_name].value
            channelValue = self.registeredChannels[channel.spec_chan_name].value
            if channelValue is not None:
                # we received a value, so emit an update signal
                channel.update(channelValue, force=True)
        except BaseException:
            logging.getLogger("SpecClient").exception(
                "Uncaught exception in SpecConnection.registerChannel"
            )

    def unregisterChannel(self, chanName):
        """Unregister a channel
        Arguments:
        chanName -- a string representing the channel to unregister, i.e. 'var/toto'
        """
        chanName = str(chanName)

        if chanName in self.registeredChannels:
            self.registeredChannels[chanName].unregister()
            del self.registeredChannels[chanName]


class SpecClient:
    def __init__(self, host, port):
        self.channel_name = None
        self.loop = asyncio.get_event_loop()
        self.transport, self.protocol = self.loop.run_until_complete(
            self.loop.create_connection(lambda: SpecProtocol(self.loop), host, port))
        self.total_time = None
        self.send_command("p \"SpecClient %s, Connected\"" % config.get('version'))
        self.sample_name = ""

    def get_data(self, property, callback=None):
        reply = self.protocol.send_msg_chan_read(property, callback=callback)
        id = reply.id
        if not callback and id > 0:
            while not self.protocol.registeredReplies[id].data:
                time.sleep(1)
        return self.protocol.registeredReplies[id].data

    def register_channel(self, channel, reciever=None):
        self.protocol.registerChannel(channel, register=True, recieverSlot=reciever)

    def send_command(self, cmd):
        self.protocol.send_msg_cmd(cmd)

    def setuser(self, username):
        self.user = username
        self.send_command("SPEC_USER = \"%s\"" % username)
        self.send_command("SPEC_USERCRED[0] = \"user=%s\"" % username)
        self.send_command("SPEC_USERCRED[1] = \"secret=%s\"" % config.get('api_key'))
        self.send_command("SPEC_USER_FLAG[0] = 1")

    def proposal(self, proposal):
        self.send_command("SPEC_PROPOSAL = \"%s\"" % proposal)
        self.send_command("SPEC_USERCRED[2] = \"proposal=%s\"" % proposal)

    def sample(self, name, kind):
        self.sample_name = name
        self.send_command("sample \"%s\" %d" % (name, kind))

    def status(self):
        self.send_command("status")

    def vent(self):
        self.send_command("vent")

    def pump_down(self):
        self.send_command("pump_down")

    def en(self, energy):
        self.send_command("umv en %d" % energy)

    def map_holder(self):
        self.send_command("cmesh xp -8 8 4 yp -5 5 25")

    def plot_holder(self, name=False):
        if PLOT_ENABLED:
            output_notebook()
            if name:
                sgmq = sgmdata.SGMQuery(sample=name, user=self.user, data=False)
            else:
                sgmq = sgmdata.SGMQuery(sample=self.sample_name, user=self.user, data=False)
            data = sgmdata.SGMData(
                sorted([p.replace('/home/jovyan/data', '/SpecData') for p in sgmq.paths],
                       key=lambda x: x.split('/')[-1].split('.')[0])[-1])
            scan = data.scans[[k for k in data.scans.keys()][0]]
            scan[[k for k in scan.__dict__.keys()][0]].plot(table=True)
        else:
            print("Plotting not currently enabled")

    def light(self, percent=20):
        self.send_command("lights %d" % percent)

    def calc_stime(self, scan):
        sp_scan = scan.split()
        if sp_scan[0] == "gscan":
            time = abs(float(sp_scan[2]) - float(sp_scan[1])) * (60 / 50) * 10 * float(sp_scan[-2])
        elif sp_scan[0] == "run_eems":
            time = 15 * 60
        elif sp_scan[0] == "cscan":
            time = float(sp_scan[4])
        elif sp_scan[0] == "ascan":
            time = float(sp_scan[4]) * float(sp_scan[5])
        elif sp_scan[0] == "cmesh":
            time = float(sp_scan[4]) * float(sp_scan[8])
        time = time * 1.5
        return time

    def make_macro(self, plate, coords=True):
        self.total_time = 0
        with open("/home/sgm/SpecMacros/plate.mac", 'w') as f:
            for n, s in enumerate(plate):
                f.write("#Entry #%d \n" % n)
                if 'det' in s.keys():
                    if 'tey' in str(s['det']).lower():
                        f.write('OPTIMIZE_TEY = 1\n')
                    if 'xeol' in str(s['det']).lower():
                        f.write('OPTIMIZE_XEOL = 1\n')
                if not isinstance(s['sample'], list):
                    s['sample'] = [s['sample']]
                if isinstance(s['coords'], tuple):
                    s['coords'] = [s['coords'] for i in range(0, len(s['sample']))]
                for i, sample in enumerate(s['sample']):
                    f.write("sample \"%s\" %d \n" % (sample, s['type']))
                    coord = s['coords'][i]
                    f.write("umv xp %f; umv yp %f \n" % coord)
                    if 'scan' in s.keys():
                        scan = s['scan']
                    elif 'scans' in s.keys():
                        scan = s['scans'][i]
                    if coords:
                        f.write("%s %f %f \n" % (scan, coord[0], coord[1]))
                    else:
                        f.write("%s \n" % scan)
                    self.total_time += self.calc_stime(scan)
                if 'det' in s.keys():
                    if 'tey' in str(s['det']).lower():
                        f.write('OPTIMIZE_TEY = 0\n')
                    if 'xeol' in str(s['det']).lower():
                        f.write('OPTIMIZE_XEOL = 1\n')
                f.write("#-------------------------------------------------------\n")
            f.write("sendmesg(\"Your macro is now complete\")")
        print("Estimated total time for this macro is %s." % str(datetime.timedelta(seconds=self.total_time)))

    def run_macro(self, path=None):
        if not self.total_time:
            print("You need to make a macro before you run a macro.")
            return
        else:
            estimate_complete = datetime.datetime.now() + datetime.timedelta(seconds=self.total_time)
            print("Estimated time of completion: %s " % estimate_complete)
        if not path:
            self.send_command("qdo /home/sgm/SpecMacros/plate.mac")
        else:
            self.send_command("qdo %s" % path)


