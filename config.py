# Python
import json
import logging

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
			d = json.load(f)
			
		if key not in d:
			raise ValueError('invalid config key: {}'.format(key))
			
		self.settings = d['shared']
		self.settings.update(d[key])
			
		# secret
		d = None
			
		with open('settings_secret.json') as f:
			d = json.load(f)
			
		if key not in d:
			raise ValueError('invalid config key: {}'.format(key))
			
		self.settings.update(d[key])
		
		logging.debug(self.settings)
			
		self.loaded = True
	
config_helper = config_helper_t()