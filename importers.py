# Python
import re
import base64
import zlib
import os
import logging
import json
import zlib
from xml import etree

# 3rd Party
import defusedxml.ElementTree as ET

# Self
import util
import pob_party

class ImporterBase:
	def is_blacklisted(self):
		if not self.initialized:
			self.init_blacklist()
	
		return self.key in self.blacklist_contents
		
	def blacklist(self):
		if not self.initialized:
			self.init_blacklist()
			
		if self.key in self.blacklist_contents:
			return
		
		self.blacklist_contents[self.key] = True
			
		logging.info("Blacklisted {}.".format(self))
			
		self.flush()
	
	# returns text contents of importer
	def contents(self):
		if not hasattr(self, '_contents'):
			self._contents = self.get_contents()
			
		return self._contents
	
	# returns xml contents of importer
	def xml(self):
		if not hasattr(self, '_xml'):
			c = self.contents()
			
			try:	
				self._xml = self.decode(c)
			except (zlib.error, TypeError, etree.ElementTree.ParseError):
				logging.info("{} does not decode to XML data.".format(self))
				self.blacklist()
				return None
			
		return self._xml
		
	def decode(self, enc):
		enc = enc.replace("-", "+").replace("_", "/")
		decoded = base64.b64decode( enc )
		
		xml_str = zlib.decompress( decoded )
		
		return ET.fromstring(xml_str)
		
	def is_pob_xml(self):
		xml = self.xml()
		
		if xml is not None:
			if xml.tag == "PathOfBuilding":
				if xml.find('Build').find('PlayerStat') is not None:
					return True
				else:
					logging.error("{} XML does not contain player stats.".format(self))
					self.blacklist()
			else:
				logging.info("{} does not contain Path of Building XML.".format(self))
				self.blacklist()
		
		return False
		
	@staticmethod
	def strip_to_key(url):
		match = re.search('\w+$', url) 
		return match.group(0)
		
	@classmethod
	def init_blacklist(cls):
		if os.path.isfile(cls.path):
			with open(cls.path, 'r') as f:
				cls.blacklist_contents = json.load(f)
				
			logging.debug("Loaded {} blacklist from {} with {} entries.".format(
				cls.__name__,
				cls.path,
				len(cls.blacklist_contents)
			))
		elif os.path.isfile("{}_blacklist.txt".format(cls.__name__.lower())):
			with open("{}_blacklist.txt".format(cls.__name__.lower())) as f:
				list = f.read()
				list = list.split("\n")
				list = filter(None, list)
				
				for entry in list:
					cls.blacklist_contents[entry] = True
					
			logging.debug("Loaded {} blacklist from {} with {} entries.".format(
				cls.__name__,
				"{}_blacklist.txt".format(cls.__name__.lower()),
				len(cls.blacklist_contents)
			))
			
			cls.flush()
		else:
			cls.blacklist_contents = {}
			logging.debug("Defaulted {} blacklist.".format(cls.__name__))
			
		cls.initialized = True
	
	@classmethod
	def flush(cls):
		with open(cls.path, 'w') as f:
			json.dump(cls.blacklist_contents, f, sort_keys=True, indent=4)
			
		logging.debug("{} blacklist saved to {}".format(cls.__name__, cls.path))

class Pastebin(ImporterBase):
	blacklist_contents = {}
	initialized = False
	path = 'save/pastebin_blacklist.json'
	
	def __init__(self, key=None, url=None):
		if not (isinstance(key, (str, unicode)) or isinstance(url, (str, unicode))):
			raise ValueError("Passed invalid args: {} {}".format(type(key), type(url)))
			
		if url is not None:
			key = self.strip_to_key(url)
			
		self.key = key
		self.url = "https://pastebin.com/{}".format(key)
		self.url_raw = "https://pastebin.com/raw/{}".format(key)
		
	def __str__(self):
		return "pastebin {}".format(self.key)
		
	def __repr__(self):
		return "<pastebin-{}>".format(self.key)
		
	# returns text contents of pastebin
	def get_contents(self):
		try:
			return util.get_url_data(self.url_raw)
		except urllib2.HTTPError as e:
			logging.error("urllib2 {:s}".format(repr(e)))
			
			if "Service Temporarily Unavailable" not in repr(e):
				self.blacklist()
				
			return None
		except urllib2.URLError as e:
			logging.error("Failed to retrieve any data\nURL: {}\n{}".format(raw_url, str(e)))
			util.dump_debug_info(wrapped_object, exc=e, paste_key=paste_key)
			return None
		
class PoBParty(ImporterBase):
	blacklist_contents = {}
	initialized = False
	path = 'save/pobparty_blacklist.json'
	
	def __init__(self, key=None, url=None):
		if not (isinstance(key, (str, unicode)) or isinstance(url, (str, unicode))):
			raise ValueError("Passed invalid args: {} {}".format(type(key), type(url)))
			
		if url is not None:
			key = self.strip_to_key(url)
			
		self.key = key
		self.url = "https://pob.party/share/{}".format(key)
		self.url_get = "https://pob.party/kv/get/{}".format(key)
		
	def __str__(self):
		return "pob.party {}".format(self.key)
		
	def __repr__(self):
		return "<pob.party-{}>".format(self.key)
		
	# returns text contents of pobparty
	def get_contents(self):
		try:
			raw = util.get_url_data(self.url_get)
			
			j = json.loads(raw)
			
			return j['data']
		except urllib2.HTTPError as e:
			logging.error("urllib2 {:s}".format(repr(e)))
			
			if "Service Temporarily Unavailable" not in repr(e):
				self.blacklist()
				
			return None
		except urllib2.URLError as e:
			logging.error("Failed to retrieve any data\nURL: {}\n{}".format(raw_url, str(e)))
			util.dump_debug_info(wrapped_object, exc=e, paste_key=paste_key)
			return None

	def xml(self):
		super().xml()

		# save the build/key combo so we don't request a new key again later
		pob_party.set_key(self)

		return self._xml
	
