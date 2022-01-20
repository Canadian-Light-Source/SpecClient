# JupyterSpecClient
Tools for running SPEC from a jupyter notebook. 

## Starting the client
```python
from spec.connection import SpecClient
sc = SpecClient('127.0.0.1', 6510)
```

## Sending Spec commands
```python
sc.send_command("umeg; umv en 900; optimize_counts")

#builtin commands
sc.setuser('regiert')
sc.status() #displays status in spec tty
sc.en(900)
sc.sample("Sample Name", 1) # 1 - sample, 2 - Reference, 3 - Normalization, 4 - Environment, 5 - None
sc.map_holder() #Will map hexapod saving under 'Sample Name' in account 'regiert'
sc.plot_holder() #Will plot last map, or you can provided keyword name=samplename
sc.make_macro(plate) #Takes dictionary created from plot_holder GUI, and creates new '~/SpecMacros/plate.mac' file
sc.run_macro() #executes sc.send_command('~/SpecMacros/plate.mac')
```

## Grabbing data
```python
import matplotlib.pyplot as plt
import numpy as np

async def plotMCA(reply):
    plt.plot(np.linspace(10, 2560, 256), reply.data, label=str(reply.cmd))

sc.protocol.send_msg_chan_read('var/MCA1_DATA', callback=plotMCA)
```