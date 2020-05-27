# Python
import random
import sys
import logging
import threading
import json
import os

# 3rd Party
import praw
import progressbar

# Self
from config import config_helper as config
config.set_mode("debug") # must set before importing other modules
import comment_maintenance
import response
import util
import stat_parsing
import item
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

		stat_parsing.init()
		item.init()
		
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
		keys = {}

		logging.info("Building importer list...")

		with progressbar.ProgressBar(max_value=self.list_size) as bar:
			while len(self._importers) < self.list_size:
				entry = self.maintain.list.pop(0)

				for importer in response.find_importers(entry.get_parent().get_body()):
					if importer.key not in keys:
						keys[importer.key] = True
						self._importers.append(importer)

				bar.update(len(self._importers))

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
				build = build_t(importer, self.reddit.user.me(), None)
				response = build.get_response()

				return True
			except EligibilityException:
				importer.blacklist()
				return False
			except Exception as e:
				logging.exception(e)
				
				# dump xml for debugging later
				#util.dump_debug_info(None, exc=e, xml=importer.xml())
				
				importer.blacklist()
				return False
		else:
			logging.debug("Skipped {} as it is not valid PoB XML.".format(importer))
			return False

	def run(self):
		successes = 0

		logging.info("Running test...")

		with progressbar.ProgressBar(max_value=self.list_size) as bar:
			for importer in self.importers:
				if self.do_test(importer):
					successes += 1
					bar.update(successes)

					if successes >= self.list_size:
						break
	

tester = unit_tester_t()

tester.run()

profile_tools.log_digest()

# Test and track