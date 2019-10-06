# Python
import json
import time
import os
import logging
import datetime

# 3rd party
from atomicwrites import atomic_write

# Self
import util

file = 'status.json'
status = {}

def update():
	status['lastUpdate'] = time.time()

	with atomic_write(file, overwrite=True) as f:
		json.dump(status, f, sort_keys=True, indent=4)
		
	logging.debug("lastUpdate set to [{}].".format(datetime.datetime.fromtimestamp(status['lastUpdate'])))
		
def get_last_update():
	try:
		return status['lastUpdate']
	except KeyError:
		logging.warning("Could not find lastUpdate in status: {}".format(status))
		return 0
	
def init():	
	if os.path.exists(file):
		with open(file, 'r') as f:
			global status
			
			try:
				status = util.byteify(json.load(f))
			except ValueError:
				pass