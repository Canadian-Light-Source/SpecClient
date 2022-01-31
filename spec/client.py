from .connection import SpecProtocol
from . import config
import time
import asyncio
import nest_asyncio

nest_asyncio.apply()
import datetime
import logging


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



class SpecClient:
    def __init__(self, host, port):
        self.channel_name = None
        self.loop = asyncio.get_event_loop()
        self.transport, self.protocol = self.loop.run_until_complete(
            self.loop.create_connection(lambda: SpecProtocol(self.loop), host, port))
        self.total_time = None
        self.send_command("p \"SpecClient %s, Connected\"" % config.get('version'))
        self.sample_name = ""
        self.plate = ""
        self.max_scans = -1

    async def get_data(self, property):
        fut = asyncio.Future()
        def callback(reply):
            if not fut.cancelled():
                fut.set_result(reply.data)
        self.protocol.send_msg_chan_read(property, callback=callback)
        return await fut

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

    def predict_remaining(self, name, value, epoch):
        """Callback for a registered channel always has the same signature: (name, value, epoch)"""
        if name == 'SCAN_WATCH' and value == 1:
            datestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(epoch))
            print(f"{datestamp} : Predicting number of scans")
            # TODO: predict number of scans, might want to instantiate a Dask client... could set the compute endpoint in config.
            pass
            # TODO: Rerun make_macro while editing self.plate to have the correct remaning number of scans, then self.run_macro()

    def make_macro10(self, plate, coords=True):
        self.make_macro(plate, coords=coords, numscans=10)

    def make_macro(self, plate, coords=True, numscans=None):
        """Creates a macro file for Spec using a plate dictionary from sgmdata
            kwargs:
                coords - indicate whether or not the plate dictionary has coordinates to start from.
                numscans - truncate the selected number of scans to N for predict_num_scans, and use requested as a max.
        """
        self.total_time = 0
        with open("/home/sgm/SpecMacros/plate.mac", 'w') as f:
            #Watch flag for macro completion.
            f.write("global SCAN_WATCH \n SCAN_WATCH = 0 \n")
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
                    if numscans and 'gscan' in scan:
                        #TODO: replace gscan column number with ceil(numscans/10), and save requested column number in self.max_scans
                        pass
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
            #Macro complete.
            f.write("SCAN_WATCH = 1 \n")
            if not numscans:
                self.max_scans = -1
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
        if self.max_scans != -1:
            self.register_channel("var/SCAN_WATCH", reciever=self.predict_remaining)

