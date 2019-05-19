# Python
import json
import time
import os
import logging
import datetime

# Self
import util

file = 'status.json'
status = {}

def update():
	status['lastUpdate'] = time.time()

	with open(file, 'w') as f:
		json.dump(status, f)
		
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