import os
import sys
from .version import __version__

cfg = {
    'version': f'{__version__}',
    'server': '127.0.0.1',
    'port': 6510
}



def get(x, sub=None):
    # see if there is a command-line override
    option = '--' + x + '='
    for i in range(1, len(sys.argv)):
        # print i, sys.argv[i]
        if sys.argv[i].startswith(option):
            # found an override
            arg = sys.argv[i]
            return arg[len(option):]  # return text after option string
    # see if there are an environment variable override
    if x.upper() in os.environ:
        return os.environ[x.upper()]
    if os.path.exists('/run/secrets/' + x):
        with open('/run/secrets/' + x, 'r') as file:
            data = file.read().replace('\n', '')
        return data
    # no command line override, just return the cfg value
    if x in cfg:
        return cfg[x]
    else:
        return sub
