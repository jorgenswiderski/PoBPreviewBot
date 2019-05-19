# Python
import json
import logging

# have to put this garbage here because dependency reasons
def byteify(input):
    if isinstance(input, dict):
        return {byteify(key): byteify(value)
                for key, value in input.iteritems()}
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input

class config_helper_t:
	def __init__(self):
		self.loaded = False
		self.settings = {}

	def __getattr__(self, name):
		return self.settings[name]
		
	def __hasattr__(self, name):
		return name in self.settings

	def set_mode(self, key):
		if self.loaded:
			raise RuntimeError('set was called too many times')
			
		d = None
			
		with open('settings.json') as f:
			d = byteify(json.load(f))
			
		if key not in d:
			raise ValueError('invalid config key')
			
		self.settings = d['shared']
		self.settings.update(d[key])
			
		# secret
		d = None
			
		with open('settings_secret.json') as f:
			d = byteify(json.load(f))
			
		if key not in d:
			raise ValueError('invalid config key')
			
		self.settings.update(d[key])
		
		logging.debug(self.settings)
			
		self.loaded = True
	
config_helper = config_helper_t()