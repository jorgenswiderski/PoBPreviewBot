import json
import time

status = {};

def update():
	status['lastUpdate'] = time.time()

	open('status.json', 'w').write(json.dumps(status))