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
import threading

# 3rd Party
import praw
import defusedxml.ElementTree as ET
from retrying import retry

# Self
from config import config_helper as config
config.set_mode('debug') # must set before importing other modules
import pastebin
import util
import status
import exceptions
import logger
import response
import replied_to
from util import obj_type_str
from comment_maintenance import maintain_list_t
from reply_buffer import reply_handler_t
from reddit_stream import stream_manager_t
from logger import init_logging

# =============================================================================
# START FUNCTION DEFINITION
	
class bot_t:
	def __init__(self):
		locale.setlocale(locale.LC_ALL, '')
		file("bot.pid", 'w').write(str(os.getpid()))

		init_logging()
		status.init()
			
		self.login()
		
		self.replied_to = replied_to.replied_t("save/replied_to.json")
		
		logging.log(logger.DEBUG_ALL, self.replied_to.dict)
		
		self.maintain_list = maintain_list_t( self, "active_comments.txt" )
			
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
		
		# initialize threading lock, which will let us pause execution in this
		# thread, and break it when our stream daemon threads find something
		self.lock = threading.Lock()
		self.condition = threading.Condition(self.lock)
		
	def is_backlogged(self):
		return self.backlog['comments'] or self.backlog['submissions']
		
	def login(self):
		logging.info("Logging in...")
		
		r = praw.Reddit(username = config.username,
			password = config.password,
			client_id = config.client_id,
			client_secret = config.client_secret,
			user_agent = "linux:PoBPreviewBot:v1.0 (by /u/aggixx)")
			
		logging.info("Successfully logged in as {:s}.".format(config.username))
			
		self.reddit = r
		
	def get_sleep_time(self):
		next_update_time = 1e10
		
		if len(self.maintain_list) > 0:
			next_update_time = min(next_update_time, self.maintain_list.next_time())
			 
		if len(self.reply_queue) > 0:
			next_update_time = min( next_update_time, self.reply_queue.throttled_until() )
		
		return next_update_time - time.time()
		
	def run(self):
		self.reply_queue.process()
		
		self.stream_manager.process()
		
		self.maintain_list.process()
		
		# If comments are in queue, then don't update status or sleep, just
		# return out so we can process them immediately
		if len(self.stream_manager) > 0:
			return
		
		# Do a status update, but only if the backlog is totally resolved.
		if not self.is_backlogged():
			status.update()
			
		# calculate the next time we need to do something
		st = self.get_sleep_time()
		
		if st > 0:
			# Put the thread to sleep, timing out after st seconds or breaking
			# out immediately if the stream manager notifies of a new entry
			logging.debug("Main thread idling for {:.3f}s or until notified".format(st))
			self.condition.acquire()
			self.condition.wait(st)
			self.condition.release()
			
	@staticmethod	
	def get_response( object ):
		return response.get_response( object )
		
	
# END FUNCTION DEFINITION
# =============================================================================
# START MAIN

bot = bot_t()

try:
	logging.info("Scanning subreddits {}...".format(config.subreddits))
	
	while True:
		bot.run()
# If ANY unhandled exception occurs, catch it, log it, THEN crash.
except BaseException:
	logging.exception("Fatal error occurred.")
	raise