# Python
import time
import os
import re
import locale
from collections import deque
import math
import random
import sys
import logging
import datetime
import _thread
import threading

# 3rd Party
import praw
import defusedxml.ElementTree as ET
from retrying import retry
#from pympler import tracker
#from pympler import asizeof

# Self
from config import config_helper as config
config.set_mode('debug') # must set before importing other modules
import util
import status
import logger
import response
import replied_to
from comment_maintenance import maintain_list_t
from reply_buffer import reply_handler_t
from reddit_stream import stream_manager_t
from logger import init_logging
import stat_parsing
import item

# =============================================================================
# START FUNCTION DEFINITION
	
class bot_t:
	def __init__(self):
		locale.setlocale(locale.LC_ALL, '')

		with open("bot.pid", 'w') as f:
			f.write(str(os.getpid()))

		init_logging()
		status.init()
			
		self.login()
		
		self.replied_to = replied_to.replied_t("save/replied_to.json")
		
		logging.log(logger.DEBUG_ALL, self.replied_to.dict)
		
		self.maintain_list = maintain_list_t( self, "save/active_comments.json" )

		stat_parsing.init()
		item.init()
			
		if '-force' in sys.argv:
			self.maintain_list.flag_for_edits(sys.argv)
		
		# Init backlog state. Stream threads will toggle these bools when they
		# have finished resolving their backlogging, allowing this main thread
		# to know when its ok to status update.
		self.backlog = {
			'comments': True,
			'submissions': True,
		}

		self.reply_queue = reply_handler_t( self )
		self.stream_manager = stream_manager_t( self )
		
		# initialize threading event, which will let us pause execution in this
		# thread whenever we want, and allow a stream subthread to signal to
		# resume execution
		self.stream_event = threading.Event()
		
		# similarly, make an acm event that main thread can use to signal the
		# ACM thread to go
		self.acm_event = threading.Event()
		
		if config.debug_memory:
			self.mem_track = tracker.SummaryTracker()
		
	def is_backlogged(self):
		return self.backlog['comments'] or self.backlog['submissions']
		
	def login(self):
		logging.info("Logging in...")
		
		if config.username == '[redacted]':
			raise ValueError("settings_secret.json is not valid.")
		
		r = praw.Reddit(username = config.username,
			password = config.password,
			client_id = config.client_id,
			client_secret = config.client_secret,
			user_agent = "linux:PoBPreviewBot:v1.0 (by /u/aggixx)")
			
		logging.info("Successfully logged in as {:s}.".format(config.username))
			
		self.reddit = r
		
	def get_sleep_time(self):
		next_update_time = time.time() + 1e6
		
		'''
		if len(self.maintain_list) > 0:
			next_update_time = min(next_update_time, self.maintain_list.next_time())
		'''
			 
		if len(self.reply_queue) > 0:
			next_update_time = min( next_update_time, self.reply_queue.throttled_until() )
		
		return next_update_time - time.time()
		
	def run(self):
		if config.debug_memory:
			self.dump_mem_summary()
	
		self.reply_queue.process()
		
		self.stream_manager.process()
		
		# Disable regular maintenance, let ACM take care of things
		#self.maintain_list.process()
		
		# If comments are in queue, then don't update status or sleep, just
		# return out so we can process them immediately
		if len(self.stream_manager) > 0:
			return
		
		# Do a status update, but only if the backlog is totally resolved.
		# Often, the stream queue will be empty but the backlog hasn't really
		# finished being processed so we aren't actually done updating.
		if not self.is_backlogged():
			status.update()
			
		# calculate the next time we need to do something
		st = self.get_sleep_time()
		
		if st > 0:
			# Put the thread to sleep, timing out after st seconds or breaking
			# out immediately if the stream manager notifies of a new entry
			logging.debug("Main thread idling for {:.3f}s or until notified".format(st))
			
			# reset the event's status
			self.stream_event.clear()
			# signal the ACM subthread that it can start maintaining comments
			self.acm_event.set()
			logging.debug("Main thread triggers acm_event.")
			# make this thread wait until a stream subthread signals this
			# thread to go, or until sleep time has elapsed
			self.stream_event.wait(timeout=st)
			
			# operation has continued, so clear the ACM flag so the subthread
			# knows to stop at the next reasonable stopping point
			self.acm_event.clear()
			logging.debug("Main thread clears acm_event.")
			
	@staticmethod	
	def get_response( object ):
		return response.get_response( object )
		
	def dump_mem_summary(self):
		if hasattr(self, 'last_mem_dump') and time.time() < self.last_mem_dump + 60:
			return
		
		gen = self.mem_track.format_diff()
		n = threading.current_thread().name
		
		for line in gen:
			logging.debug("[{}] {}".format(n, line))
			
		# ---
		
		logging.debug("bot={}b replied_to={} maintain.list={} maintain.rlist={} rq.queue={} sm.list={} sm.processed={}".format(
			asizeof.asizeof(self),
			asizeof.asizeof(self.replied_to),
			len(self.maintain_list.list),
			len(self.maintain_list.retired_list),
			len(self.reply_queue.queue),
			len(self.stream_manager.list),
			["{}/{}".format(len(t.processed), asizeof.asizeof(t.processed)) for t in self.stream_manager.threads]
		))
		
	
# END FUNCTION DEFINITION
# =============================================================================
# START MAIN

try:
	bot = bot_t()
	logging.info("Scanning subreddits {}...".format(config.subreddits))
	
	while True:
		bot.run()
# If ANY unhandled exception occurs, catch it, log it, THEN crash.
except BaseException:
	logging.exception("Fatal error occurred.")
	raise