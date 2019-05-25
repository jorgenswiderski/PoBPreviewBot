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

class Pastebin:
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
		
	# returns text contents of pastebin
	def contents(self):
		if not hasattr(self, '_contents'):
			try:
				self._contents = util.get_url_data(self.url_raw)
			except urllib2.HTTPError as e:
				logging.error("urllib2 {:s}".format(repr(e)))
				
				if "Service Temporarily Unavailable" not in repr(e):
					self.blacklist()
					
				return None
			except urllib2.URLError as e:
				logging.error("Failed to retrieve any data\nURL: {}\n{}".format(raw_url, str(e)))
				util.dump_debug_info(wrapped_object, exc=e, paste_key=paste_key)
				return None
			
		return self._contents
	
	# returns xml contents of pastebin
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
		
		try:
			xml_str = zlib.decompress( decoded )
		except zlib.error:
			pass
		
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
	def init_blacklist():
		if os.path.isfile(Pastebin.path):
			with open(Pastebin.path, 'r') as f:
				Pastebin.blacklist_contents = json.load(f)
				
			logging.debug("Loaded pastebin blacklist from {} with {} entries.".format(
				Pastebin.path,
				len(Pastebin.blacklist_contents)
			))
		elif os.path.isfile('pastebin_blacklist.txt'):
			with open('pastebin_blacklist.txt') as f:
				list = f.read()
				list = list.split("\n")
				list = filter(None, list)
				
				for entry in list:
					Pastebin.blacklist_contents[entry] = True
					
			logging.debug("Loaded pastebin blacklist from {} with {} entries.".format(
				'pastebin_blacklist.txt',
				len(Pastebin.blacklist_contents)
			))
			
			Pastebin.flush()
		else:
			Pastebin.blacklist_contents = {}
			logging.debug("Defaulted pastebin blacklist.")
			
		Pastebin.initialized = True
	
	@staticmethod
	def flush():
		with open(Pastebin.path, 'w') as f:
			json.dump(Pastebin.blacklist_contents, f, sort_keys=True, indent=4)
			
		logging.debug("Pastebin blacklist saved to {}".format(Pastebin.path))
		
	@staticmethod
	def strip_to_key(url):
		match = re.search('\w+$', url)
		paste_key = match.group(0)
		return paste_key