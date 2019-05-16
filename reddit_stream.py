# Python
import threading
import logging
import os
import time
import datetime

# 3rd Party
import praw

# Self
import util
import official_forum
import config
import status
from praw_wrapper import praw_object_wrapper_t
from response import blacklist_pastebin
from response import get_response
from response import reply_to_summon

class stream_thread_t(threading.Thread):
	def __init__(self, manager, type):
		threading.Thread.__init__(self)
		
		if not hasattr(manager.subreddit.stream, type):
			raise ValueError("stream_thread_t was passed invalid type")

		self.manager = manager
		self.type = type
		self.handler = getattr(manager.subreddit.stream, type)
		self.processed = {}
		
		logging.debug("Created thread {} {}".format(self.manager.subreddit_str, self.type))
				
	def get_backlog_window(self):
		return max(status.get_last_update(), time.time() - config.backlog_time_limit)
			
	def check_and_queue(self, object):
		#logging.debug("Found {}".format(str(object)))
	
		if object.id in self.processed:
			return
		
		self.processed[object.id] = True
			
		if object.id in self.manager.bot.replied_to[self.type]:
			return
		
		wrapped = praw_object_wrapper_t(object)
			
		self.manager.list.append(wrapped)
		logging.debug("Added {} to stream queue (len={}).".format(str(wrapped), len(self.manager.list)))
		
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
				
	def do_backlog(self):
		since = self.get_backlog_window()
		logging.info("Pulling {} since [{}]...".format(self.type, str(datetime.datetime.fromtimestamp(since))))
		
		# Grab comments
		backlogged = getattr(self.manager.subreddit, 'new' if self.type == 'submissions' else 'comments')
		count = 0
		
		for object in backlogged():
			if object.created_utc < since:
				logging.info("Completed pulling {} backlog, checked {} {}.".format(self.type, count, self.type))
				return
				
			count = count + 1;
			
			self.check_and_queue(object)

	def run(self):
		logging.debug("Started thread {} {}".format(self.manager.subreddit_str, self.type))
		
		self.do_backlog()
		
		for object in self.handler(skip_existing=True):
			self.check_and_queue(object)

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
				logging.debug("{} author is self, ignoring".format(str(object)))
				continue
						
			replied = object.parse_and_reply(self.reply_queue)
			
			if not replied and object.is_comment() and ( "u/" + config.username ).lower() in object.get_body().lower():
				reply_to_summon( self.bot, object )
			
			
			
			
			