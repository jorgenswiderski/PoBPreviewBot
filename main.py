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
import live_config as config
import live_secret_config as sconfig
#import config
#import secret_config as sconfig
import pastebin
import util
import status
import exceptions
import logger
import response
from util import obj_type_str
from comment_maintenance import maintain_list_t
from reply_buffer import reply_handler_t
from reddit_stream import stream_manager_t
from logger import init_logging

# =============================================================================
# START FUNCTION DEFINITION
			
def get_saved_comments():
	if not os.path.isfile("comments_replied_to.txt"):
		comments_replied_to = []
	else:
		with open("comments_replied_to.txt", "r") as f:
			comments_replied_to = f.read()
			comments_replied_to = comments_replied_to.split("\n")
			comments_replied_to = filter(None, comments_replied_to)
		
	return comments_replied_to
			
			
def get_saved_submissions():
	if not os.path.isfile("submissions_replied_to.txt"):
		submissions_replied_to = []
	else:
		with open("submissions_replied_to.txt", "r") as f:
			submissions_replied_to = f.read()
			submissions_replied_to = submissions_replied_to.split("\n")
			submissions_replied_to = filter(None, submissions_replied_to)
		
	return submissions_replied_to
	
class bot_t:
	def __init__(self):
		locale.setlocale(locale.LC_ALL, '')
		file("bot.pid", 'w').write(str(os.getpid()))

		init_logging()
		status.init()
			
		self.login()
		
		self.replied_to = {
			'comments': get_saved_comments(),
			'submissions': get_saved_submissions(),
		}
		
		logging.log(logger.DEBUG_ALL, self.replied_to['comments'])
		logging.log(logger.DEBUG_ALL, self.replied_to['submissions'])
		
		self.maintain_list = maintain_list_t( self, "active_comments.txt" )
			
		if '-force' in sys.argv:
			maintain_list.flag_for_edits(sys.argv)

		self.reply_queue = reply_handler_t( self )
		self.stream_manager = stream_manager_t( self )
		
		# initialize threading lock, which will let us pause execution in this
		# thread, and break it when our stream daemon threads find something
		self.lock = threading.Lock()
		self.condition = threading.Condition(self.lock)
		
	def login(self):
		logging.info("Logging in...")
		
		r = praw.Reddit(username = config.username,
			password = sconfig.password,
			client_id = sconfig.client_id,
			client_secret = sconfig.client_secret,
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