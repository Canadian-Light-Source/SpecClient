# SpecClient
Tools for handling a connection to SPEC server, implimented in asyncio.  Largely borrowed from [BLISS's comms](https://gitlab.esrf.fr/bliss/bliss/-/tree/master/bliss/comm).

## Starting the client

```python
from specc import Client

sc = Client('127.0.0.1', 6510) #Or set server & port in config.py, and simply execute Client()
```

## Sending Spec commands
```python
sc.send_command("umeg; umv en 900; optimize_counts")
```

## Subscribe to channel with Callback
```python
from ipywidgets import Text
from Ipython.display import display

txt = Text(disabled=True)

def disp_mot_position(name, value, epoch):
    if isinstance(value, str):
        txt.value = f"{name}: {value} @ {epoch}"

sc.register_channel("motor/en/position", callback=disp_mot_position)
display(txt)
```

## Grabbing data with Callback
```python
import matplotlib.pyplot as plt
import numpy as np

async def plotMCA(reply):
    plt.plot(np.linspace(10, 2560, 256), reply.data, label=str(reply.cmd))

sc.channel_read('var/MCA1_DATA', callback=plotMCA)
```

## Grabbing data on demand
```python
arr = await sc.get_data('var/MCA2_DATA')
```
