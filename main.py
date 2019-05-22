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
import thread
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
from comment_maintenance import maintain_list_t
from reply_buffer import reply_handler_t
from reddit_stream import stream_manager_t
from logger import init_logging

# =============================================================================
# START FUNCTION DEFINITION

'''
def dthread(bot):
	while True:
		rl = bot.reddit._core._rate_limiter
		
		logging.info(rl.__dict__)
		
		time.sleep(1)
'''
	
class bot_t:
	def __init__(self):
		locale.setlocale(locale.LC_ALL, '')
		file("bot.pid", 'w').write(str(os.getpid()))

		init_logging()
		status.init()
			
		self.login()
		
		self.replied_to = replied_to.replied_t("save/replied_to.json")
		
		logging.log(logger.DEBUG_ALL, self.replied_to.dict)
		
		# make a primitive lock for aggressive comment maintenance. the main
		# thread will acquire the lock whenever it is doing anything, then
		# release it whenever it idles. the aggressive maintenance thread will
		# acquire whenever it starts maintaining an entry, then release it
		# whenever it finishes.
		self.acm_lock = thread.allocate_lock()
		self.acm_lock.acquire()
		logging.debug("MainThread acquired acm_lock.")
		
		self.maintain_list = maintain_list_t( self, "save/active_comments.json" )
			
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
		
		'''
		dt = threading.Thread(target=dthread, name='DebugThread', args=(self,))
		dt.daemon = True
		dt.start()
		'''
		
	def is_backlogged(self):
		return self.backlog['comments'] or self.backlog['submissions']
			
	'''
	def is_rate_limited(self):
		# prawcore.sessions.Session object
		# see: prawcore/sessions.py
		session = self.reddit._core
		
		# prawcore.rate_limit.RateLimiter object
		# see: prawcore/rate_limit.py
		rl = session._rate_limiter
		
		# stores the time at which the next request can be performed. if the
		# session is not throttled, this value will be None.
		nrt = rl.next_request_timestamp
		
		return nrt is not None
	'''
		
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
			# release the aggressive comment maintenance lock, which will allow the ACM thread to start
			self.acm_lock.release()
			logging.debug("MainThread released acm_lock.")
			# make this thread wait until a stream subthread signals this
			# thread to go, or until sleep time has elapsed
			self.stream_event.wait(st)
			
			# operation has continued, so time to reclaim the ACM lock
			if self.acm_lock.locked():
				logging.debug("MainThread waiting to acquire acm_lock.")
			
			self.acm_lock.acquire()
			logging.debug("MainThread acquired acm_lock.")
			
	@staticmethod	
	def get_response( object ):
		return response.get_response( object )
		
	
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