# Python
import thread
import threading
import logging
import os
import time
import datetime
import math

# 3rd Party
import praw
from retrying import retry

# Self
import util
import official_forum
from config import config_helper as config
import status
import logger
from praw_wrapper import praw_object_wrapper_t
from response import blacklist_pastebin
from response import get_response
from response import reply_to_summon

class stream_thread_t(threading.Thread):
	def __init__(self, manager, type):
		threading.Thread.__init__(self, name="{}Thread".format(type))
		
		if not hasattr(manager.subreddit.stream, type):
			raise ValueError("stream_thread_t was passed invalid type")

		self.manager = manager
		self.type = type
		self.handler = getattr(manager.subreddit.stream, type)
		self.processed = {}
		
		logging.debug("Created {} daemon thread.".format(self.type))
				
	def get_backlog_window(self):
		return max(status.get_last_update(), time.time() - config.backlog_time_limit)
			
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)
	def check_and_queue(self, object):
		logging.log(logger.DEBUG_ALL, "{} daemon thread found {}.".format(self.type, object))
		
		if object.id in self.processed:
			logging.debug("{} has already been processed.".format(object))
			return
			
		if self.manager.bot.replied_to.contains(object):
			logging.debug("{} has already been replied to.".format(object))
			self.processed[object.id] = True
			return
		
		wrapped = praw_object_wrapper_t(self.manager.bot, object)
			
		self.manager.list.append(wrapped)
		self.processed[object.id] = True
		logging.debug("Added {} to stream queue (len={}).".format(wrapped, len(self.manager.list)))
		
		try:
			if util.get_num_waiters(self.manager.bot.condition) > 0:
				# Notify the main thread to wake up so it can process the new entry
				self.manager.bot.condition.acquire()
				self.manager.bot.condition.notify()
				self.manager.bot.condition.release()
				logging.debug("{} thread notified main thread".format(self.type))
		except RuntimeError:
			logging.warn("{} thread failed to notify main thread".format(self.type))
			pass
				
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)	
	def do_backlog(self, since):
		
		# Grab comments
		backlogged = getattr(self.manager.subreddit, 'new' if self.type == 'submissions' else 'comments')
		count = 0
		
		# Docs say that no limit may be limited to 1000 objects anyway.
		# https://praw.readthedocs.io/en/latest/code_overview/other/listinggenerator.html#praw.models.ListingGenerator
		for object in backlogged(limit=None):
			if object.created_utc < since:
				# flag backlog as resolved in bot state
				self.manager.bot.backlog[self.type] = False
				logging.info("Completed pulling {} backlog, checked {} {}.".format(self.type, count, self.type))
				return
				
			count = count + 1;
			
			self.check_and_queue(object)
			
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)	
	def do_stream(self):
		for object in self.handler():
			self.check_and_queue(object)

	def run(self):
		# Exception handler shell
		try:
			self.main()
		# If ANY unhandled exception occurs, catch it, log it, THEN crash.
		except BaseException:
			logging.exception("Fatal error occurred in {} thread.".format(self.type))
			thread.interrupt_main()
			raise
			
	def main(self):
		logging.debug("Started {} daemon thread.".format(self.type))
		
		since = self.get_backlog_window()
		logging.info("Pulling {} since [{}]...".format(
			self.type,
			datetime.datetime.fromtimestamp(math.floor(since))
		))
		self.do_backlog(since)
		
		self.do_stream()
			
	

class stream_manager_t:
	def __init__(self, bot):
		self.bot = bot
		self.reddit = bot.reddit
		self.subreddit_str = "+".join(config.subreddits)
		self.subreddit = self.reddit.subreddit(self.subreddit_str)
		self.reply_queue = bot.reply_queue
		
		self.list = []
		self.threads = []
		
		self.__init_threads__()
		
	def __init_threads__(self):
		self.threads.append(stream_thread_t(self, 'comments'))
		self.threads.append(stream_thread_t(self, 'submissions'))
		
		for thread in self.threads:
			thread.daemon = True
			thread.start()
		
	def __len__(self):
		return len(self.list)
		
	def is_active(self):
		return len(self) > 0
		
	def process(self):
		while self.is_active():
			# pop the first object
			object = self.list.pop(0)
			
			if self.reply_queue.contains_id(object.id):
				continue
				
			if object.author == self.reddit.user.me():
				logging.debug("{} author is self, ignoring".format(object))
				continue
						
			replied = object.parse_and_reply(self.reply_queue)
			
			if not replied and object.is_comment() and ( "u/" + config.username ).lower() in object.get_body().lower():
				reply_to_summon( self.bot, object )
			
			
			
			
			