# Python
import random
import sys
import logging
import threading
import json
import os

# 3rd Party
import praw

# Self
from config import config_helper as config
config.set_mode('debug') # must set before importing other modules
import comment_maintenance
import response
import util
from importers import ImporterEncoder, Pastebin, PoBParty
import profile_tools
from profile_tools import profile_cumulative, profile, ChunkProfiler
from pob_build import build_t
from _exceptions import EligibilityException

logging.root.setLevel(logging.INFO)

# Create bot dummy object
class unit_tester_t:
	def __init__(self):
		self.login()
		self.replied_to = None
		self.acm_event = threading.Event()
		self.maintain = comment_maintenance.maintain_list_t(self, "save/active_comments.json.server")
		self.list_size = 20
		
	def login(self):
		logging.info("Logging in...")
		
		if config.username == '[redacted]':
			raise ValueError("settings_secret.json is not valid.")
		
		r = praw.Reddit(username = config.username,
			password = config.password,
			client_id = config.client_id,
			client_secret = config.client_secret,
			user_agent = "linux:PoBPreviewBot-UnitTest:v1.0 (by /u/aggixx)")
			
		logging.info("Successfully logged in as {:s}.".format(config.username))
			
		self.reddit = r

	def build_importer_list(self):
		self.maintain.lock.acquire()

		random.shuffle(self.maintain.list)

		self._importers = []

		while len(self._importers) < self.list_size:
			entry = self.maintain.list.pop(0)

			for importer in response.find_importers(entry.get_parent().get_body()):
				self._importers.append(importer)

		self.maintain.lock.release()

		random.shuffle(self._importers)

		with open('save/unit_test.json', 'w') as f:
			json.dump(self._importers, f, cls=ImporterEncoder, sort_keys=True, indent=4)

	def load_importer_list(self):
		if not os.path.isfile('save/unit_test.json'):
			return

		with open('save/unit_test.json', 'r') as f:
			data = json.load(f)

		self._importers = []

		for datum in data:
			if datum['class'] == 'Pastebin':
				self._importers.append(Pastebin(key=datum['key']))
			elif datum['class'] == 'PoBParty':
				self._importers.append(PoBParty(key=datum['key']))

	@property
	def importers(self):
		if not hasattr(self, '_importers'):
			self.load_importer_list()

		if not hasattr(self, '_importers') or len(self._importers) < self.list_size:
			self.build_importer_list()

		return self._importers

	@profile_cumulative
	def do_test(self, importer):
		if importer.is_pob_xml():
			build = None

			try:
				build = build_t(importer, author, None)
				response = build.get_response()
			except EligibilityException:
				importer.blacklist()
				raise
				return
			except Exception as e:
				logging.error(repr(e))
				
				# dump xml for debugging later
				#util.dump_debug_info(None, exc=e, xml=importer.xml())
				
				importer.blacklist()
				return
			
			#if config.xml_dump:
			#	util.dump_debug_info(None, xml=importer.xml(), dir="xml_dump", build=build)
				
			responses.append(response)
			importers_responded_to[importer.key] = True
		else:
			logging.debug("Skipped {} as it is not valid PoB XML.".format(importer))

	def run(self):
		for importer in self.importers:
			self.do_test(importer)
	

tester = unit_tester_t()

tester.run()

profile_tools.log_digest()

# Test and track