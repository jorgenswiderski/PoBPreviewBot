# Python
import time
import os
import random
import math
import thread
import threading
import datetime
import json
import logging
import copy

# 3rd Party
import praw
import urllib2
from retrying import retry
from pympler import asizeof

from prawcore.exceptions import Forbidden
from praw.exceptions import APIException

# Self
import util
import logger
from config import config_helper as config
import official_forum
from praw_wrapper import praw_object_wrapper_t

from _exceptions import ImporterLimitException
from _exceptions import EligibilityException

# =============================================================================

not_author_blacklist = {};

class entry_encoder_t(json.JSONEncoder):
	def default(self, obj):
		if isinstance(obj, entry_t):
			return {
				'comment_id': obj.comment_id,
				'time': obj.time,
				'created_utc': obj.created_utc,
				'last_time': obj.last_time,
				'retired': obj.retired,
			}
		return json.JSONEncoder.default(self, obj)
		
class entry_t:
	def __init__(self, list, jdict):
		self.list = list
		self.bot = list.bot
		
		self.__dict__.update(jdict)
		
		self.comment = None
		self.parent = None
		
		if not hasattr(self, 'time'):
			#logging.warning("Entry {} initialized without 'time' attribute!".format(self.comment_id))
			self.update_check_time()
			
		if not hasattr(self, 'last_time'):
			#logging.warning("Entry {} initialized without 'last_time' attribute!".format(self.comment_id))
			self.last_time = 0
		
		if not hasattr(self, 'retired'):
			#logging.warning("Entry {} initialized without 'retired' attribute!".format(self.comment_id))
			self.retired = self.get_age() >= config.preserve_comments_after
			
	def asizeof(self):
		b = 0
		
		if self.comment is not None:
			b += 1
			
		if self.parent is not None:
			b += 1
		
		return b
		
	@classmethod
	def from_str(cls, list, str):
		split = str.strip().split('\t')
		
		return cls(list, split[0], split[2], time=split[1], last_time=split[3])
		
	def __str__(self):
		return "entry {}".format(self.comment_id)
			
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)
	def get_comment(self):
		if self.comment is None:
			comment = util.get_praw_comment_by_id(self.list.reddit, self.comment_id)
			self.comment = praw_object_wrapper_t(self.bot, comment)
		
			# Fetch the comment now in a place where RequestExceptions can be handled properly.
			if not self.comment._fetched:
				self.comment._fetch()
			
		return self.comment
			
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)
	def get_parent(self):
		if self.parent is None:
			self.parent = self.get_comment().parent()
		
			# Fetch the comment now in a place where RequestExceptions can be handled properly.
			if not self.parent._fetched:
				self.parent._fetch()
			
		return self.parent
	
	@staticmethod
	def get_check_time(comment_age):
		# 0 < x < 15 minutes
		# fixed interval of 60s
		t = 60
		
		# 15m < x < 4h
		if comment_age > 900:
			# increase linearly up to 15 minutes
			t *= min( comment_age, 14400 ) / ( 14400 / 15 )
			
		# 4h < x < 1w
		if comment_age > 14400:
			# increase exponentially up to 6 hours
			t *= math.pow( 1.078726, ( min( comment_age, 604800 ) - 900 ) / 14400 )
			
		if comment_age > 604800:
			# 2 weeks: 15.1 hrs
			# 3 weeks: 24.0 hrs
			# 4 weeks: 38.1 hrs
			# 4.585+ weeks: 72 hrs
			t *= min( math.pow( 2, ( comment_age - 604800 ) / 604800 ), 12 )
			
		if config.deletion_check_interval_rng > 0:
			t *= 1.0 + config.deletion_check_interval_rng * ( 2.0 * random.random() - 1.0 )
			
		return t
		
	def get_age(self):
		return time.time() - self.created_utc
		
	def update_check_time(self):
		self.time = time.time() + entry_t.get_check_time(self.get_age())
		
	def flag(self):
		self.time = 0
		
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)	
	def __refresh__(self, object):
		try:
			if isinstance(object, praw.models.Comment):
				object.refresh()
			else:
				# There doesn't seem to be a way to refresh a submission, so we
				# have to use the internal function "fetch"
				object._fetch()
		except praw.exceptions.ClientException as e:
			# Dump info
			logging.warning("ClientException occurred when refreshing for maintenance of comment {}".format(self.comment_id))
			util.dump_debug_info(object, exc=e, extra_data={
				'entry_t': json.dumps(self.__dict__),
			})
			
			# Reraise the exception so refresh() knows we failed
			raise e
		
	def refresh(self):
		try:
			if self.comment is not None:
				self.__refresh__(self.comment)
				
			if self.parent is not None:
				self.__refresh__(self.parent)
		except praw.exceptions.ClientException:
			return False
			
		return True
	
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)	
	def maintain(self):
		# Whether the comment has been deleted, and therefore doesn't need to
		# be maintained anymore.
		deleted = False
		# Whether we failed to maintain the comment, and therefore need to check it again soon.
		failure = False
		
		if self.comment_id in not_author_blacklist:
			failure = True
		else:
			logging.debug("Maintaining comment {:s}.".format( self.comment_id ))
			
			# if we've already made a comment object, then
			# force refresh on the comment, otherwise we won't be able to detect any changes
			if self.refresh():
				# Make sure the reply has not already been deleted
				if self.get_comment().body == "[deleted]":
					logging.warning("Reply {} has already been deleted, removing from list of active comments.".format(self.comment_id))
					deleted = True
				
				try:
					if not deleted:
						deleted = self.check_for_deletion()

					if not deleted:
						deleted = self.check_for_edit()
				except urllib2.HTTPError as e:
					logging.error("An HTTPError occurred while maintaining comment {}. Skipping the check for now.".format(self.comment_id))
				except Forbidden as e:
					logging.error("Attempted to perform forbidden action on comment {:s}. Removing from list of active comments.\n{:s}".format(self.comment_id, self.get_comment().permalink()))
					# Comment may or may not be deleted, but for one reason or another we can't modify it anymore, so no point in trying to keep track of it.
					deleted = True
			else:
				failure = True
				
		if not deleted:
			if self.get_age() < config.preserve_comments_after:
				# calculate the next time we should perform maintenance on this comment
				self.update_check_time()
				
				if failure:
					# If there was a failure to maintain the comment, postpone
					# trying it again for 10 minutes. This will hopefully prevent
					# chain failures from blocking or saturating the queue.
					fail_time = time.time() + 600
					
					if fail_time < self.time:
						self.time = fail_time
				
				self.last_time = time.time()
				
				# reinsert the entry at its chronologically correct place in the list
				self.list.add_entry(self)	
			else:
				self.retire()
				
		# free memory if this entry isn't going to be visited very soon
		# we have to fetch new data anyway so keeping the old object around
		# probably doesn't do much. and having several thousand comment
		# objects in memory at all times isnt doing us any favors
		if self.retired or self.time - time.time() > 900:
			self.comment = None
			self.parent = None
				
	def retire(self):
		self.retired = True
		self.list.retired_list.append(self)
			
	def check_for_deletion(self):
		comment = self.get_comment()
		parent = self.get_parent()
		
		if comment.is_root:
			if parent.selftext == "[deleted]" or parent.selftext == "[removed]":
				comment.delete()
				logging.info("Deleted comment {:s} as parent submission {:s} was deleted.".format( self.comment_id, parent.id ))
				
				return True
		else:
			if parent.body == "[deleted]":
				comment.delete()
				logging.info("Deleted comment {:s} as parent comment {:s} was deleted.".format( self.comment_id, parent.id ))
				
				return True
				
		return False

	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)	
	def check_for_edit(self):
		parent = self.get_parent()
		comment = self.get_comment()
		
		# has the comment been edited recently OR the comment is new (edit tag is not visible so we need to check to be safe)
		# grace period is apparently 180 seconds, but lets check for a bit longer to be safe
		
		if ( isinstance(parent.edited, float) and parent.edited >= self.last_time - 10 ) or time.time() - parent.created_utc < 400 or ( comment.is_root and parent.selftext == '' and official_forum.is_post( parent.url ) ) or self.time == 0:
			new_comment_body = None
			
			try:
				new_comment_body = self.bot.get_response( parent )
			except (EligibilityException, ImporterLimitException) as e:
				print(e)
			
			if new_comment_body is None:
				comment.delete()
				logging.info("Parent {:s} no longer links to any builds, deleted response comment {:s}.".format(parent.id, self.comment_id))
				
				if self.list.replied_to.contains(parent.id):
					self.list.replied_to.remove(parent.id)
					
				return True
			elif new_comment_body != comment.body:
				try:
					comment.edit(new_comment_body)
					logging.info("Edited comment {:s} to reflect changes in parent {:s}.".format(self.comment_id, parent.id))
				except APIException as e:
					if "NOT_AUTHOR" in str(e):
						logging.warning("Attempted to modify comment {} that we do not own. Ignoring for the remainder of this execution.".format(self.comment_id))
						not_author_blacklist[self.comment_id] = True
					else:
						raise e
			else:
				logging.debug("{:s}'s response body is unchanged.".format(parent.id))
		else:
			if isinstance(parent.edited, float):
				time_since_edit = math.ceil(time.time() - parent.edited)
				seconds_before_cutoff = math.ceil(self.time - 60 - parent.edited)
				logging.debug("{} was last edited [{}] ago ([{}] before the edit window).".format(parent, datetime.timedelta(seconds=time_since_edit), datetime.timedelta(seconds=seconds_before_cutoff)))
			elif time.time() - parent.created_utc >= 400:
				age = math.ceil(time.time() - parent.created_utc)
				logging.debug("{} is more than 400s old [{}] and is not edited.".format(parent, datetime.timedelta(seconds=age)))	
				
		return False
		
	# Returns a float that represents the percentage of time that has elapsed
	# towards the next maintainance
	def get_progress(self):
		elapsed = time.time() - self.last_time
		dur = self.time - self.last_time
		
		#logging.debug("id={} elapsed={} dur={}".format(self.comment_id, elapsed, dur))
		
		return elapsed / dur
		
class aggressive_maintainer_t(threading.Thread):
	rate_limit_window = 600
	
	def __init__(self, list):
		threading.Thread.__init__(self, name='ACMThread')
		
		self.list = list
		self.bot = list.bot
		# the max amount of the rate limit to utilize.
		# ie: 0.80 means we stop maintaining more comments once we reach 80%
		# utilized of the max query amount
		self.amu = config.aggressive_maintenance_utilization
		
		logging.debug("Created ACM daemon thread.")
	
	# Get Rate Limit utilization
	# Returns a percent (float) that represents the projected number of queries
	# relative to the maximum number of queries for the current rate limit
	# period. For example:
	# 0.50 would mean that its projected that only half the max queries will be used
	# 1.50 would mean that its projected that we will exceed the max queries and get throttled
	def get_rl_utilization(self):
		rl = self.bot.reddit._core._rate_limiter
		
		# rate limit window end timestamp
		end = rl.reset_timestamp
		# rate limit window start timestamp (assumed)
		start = end - self.rate_limit_window
		# elapsed time
		elapsed = time.time() - start
		elapsed_pct = elapsed / self.rate_limit_window
		
		if elapsed_pct == 0:
			return 1.0
		
		queries_total = rl.used + rl.remaining
		
		if queries_total == 0:
			return 1.0
		
		used_pct = rl.used / queries_total
		
		logging.log(logger.DEBUG_ALL, "used={:.0f} rem={:.0f} total={:.0f} start={:.3f} end={:.3f} elapsed={:.3f} el_pct={:.2f}% used_pct={:.2f}% util={:.2f}%".format(
			rl.used, rl.remaining, queries_total,
			start, end, elapsed,
			elapsed_pct*100, used_pct*100, used_pct / elapsed_pct * 100 ) )
		
		return used_pct / elapsed_pct
		
	def sleep(self):
		rl = self.bot.reddit._core._rate_limiter
		
		# rate limit window end timestamp
		end = rl.reset_timestamp
		# rate limit window start timestamp (assumed)
		start = end - self.rate_limit_window
		
		queries_total = rl.used + rl.remaining
		used_pct = rl.used / queries_total
		
		ready_time = start + self.rate_limit_window * min( 1.0, used_pct / self.amu )
		
		# add 10ms to avoid rounding issues causing excessive cycles
		dur = ready_time - time.time() + 0.01
		
		if dur >= 0:
			logging.debug("ACMThread idling for {:.3f}s.".format(dur))
			time.sleep(dur)
			
	def wait_for_init(self):
		rl = self.bot.reddit._core._rate_limiter
		
		while rl.remaining is None or rl.used is None or rl.reset_timestamp is None:
			time.sleep(1)
			
	def choose(self):
		val = -1
		highest = None
		
		# filter to entries that haven't been checked in at least 35 seconds
		# praw caches content for 30 seconds so there is literally no point in
		# doing it more often than that
		now = time.time()
		
		for entry in filter(lambda e: now - e.last_time >= 35, self.list.list): 
			prog = entry.get_progress()
			
			if prog > val:
				val = prog
				highest = entry
				
		logging.debug("Highest entry is {} at {:.2f}% progress. Current ACM rate is {:.2f}x.".format(highest, val*100, 1/val))
				
		return highest
		
	def main(self):
		# Wait for the rate limiter to initialize
		self.wait_for_init()
		
		logging.debug("ACM has initialized.")
		
		while True:
			# Wait for a signal from main thread to begin
			# As long as main thread is asleep, this call will return immediately.
			# If main thread is awake, it will return as soon as it goes to sleep.
			self.bot.acm_event.wait()
			
			while self.get_rl_utilization() < self.amu and len(self.list) > 0:
				# choose the entry we will maintain
				entry = self.choose()
				
				self.list.list.remove(entry)
				
				entry.maintain()
				
				# write the updated maintenance list to file
				self.list.flush()
				
				if config.debug_memory:
					items = sum(map(lambda x: x.asizeof(), self.list.list))
					
					logging.debug("# of cached items: {}".format(items))
				
			self.sleep()
			
	def run(self):
		logging.debug("Started ACM daemon thread.")
		
		# Exception handler shell
		try:
			self.main()
		# If ANY unhandled exception occurs, catch it, log it, THEN crash.
		except BaseException:
			logging.exception("Fatal error occurred in ACMThread.")
			thread.interrupt_main()
			raise
		
class maintain_list_t:
	def __init__(self, bot, file_path):
		self.bot = bot
		self.file_path = file_path
		self.reddit = bot.reddit
		self.replied_to = bot.replied_to
		
		self.list = []
		self.retired_list = []
		
		if not os.path.isfile(file_path):
			self.list = []
		else:
			#self.__init_from_file__()
			self.__init_from_json__()
			self.sort()
		
		if config.aggressive_maintenance_utilization > 0:
			self.thread = aggressive_maintainer_t(self)
			self.thread.daemon = True
			self.thread.start()
		else:
			logging.debug("ACM is disabled.")
			
	def __init_from_json__(self):
		processed = {}
	
		with open(self.file_path, 'r') as f:
			list = util.byteify(json.load(f))
			
			for jdict in list:
				if jdict['comment_id'] in processed:
					continue
			
				entry = entry_t(self, jdict)
				
				# Only append to list if the comment is young enough
				if entry.retired:
					self.retired_list.append( entry )
					logging.debug( "Did not add comment {} to maintain list (too old)".format(entry.comment_id) )
				else:
					self.list.append( entry )
					
				processed[entry.comment_id] = True
			
			logging.debug("Populated maintain_list_t with {} active entries, {} retired entries.".format(len(self), len(self.retired_list)))
		
	def __len__(self):
		return len(self.list)
	
	@staticmethod
	def sorter(a):
		return a.time
		
	def sort(self):
		self.list.sort(key=maintain_list_t.sorter)
		
	def binary_insert(self, entry):
		# binary search for the index to insert at
		
		# define search boundaries
		lower = -1
		upper = len(self)
		
		# while our boundaries have not crossed
		while abs( lower - upper ) > 1:
			# take the average
			middle = int( math.floor( ( lower + upper ) / 2  ) )
			
			# move the upper or lower boundary to halve the search space
			if self.list[middle].time > entry.time:
				upper = middle
			else:
				lower = middle
				
		logging.debug("Inserting {:s} into maintain list at idx={:.0f} to be refreshed at [{}].".format(entry.comment_id, upper, datetime.datetime.fromtimestamp(entry.time)))
		'''
		if lower >= 0:
			logging.info(float(deletion_check_list[lower]['time']))
		if upper < len(deletion_check_list):
			logging.info(float(deletion_check_list[upper]['time']))
		'''
			
		self.list.insert(upper, entry)
			
	def add(self, comment):
		entry = entry_t(self, {
			"comment_id": comment.id,
			"created_utc": comment.created_utc,
		})
		
		self.add_entry( entry )
			
	def add_entry(self, entry):
		self.binary_insert( entry )

	def flag_for_edits(self, args):
		if not ( '-force' in args and args.index('-force') < len(args) ):
			return
		
		time_str = args[ args.index('-force') + 1 ]
		cutoff = time.time() - util.parse_time_str(time_str)
		
		filtered = filter(lambda x: x.created_utc >= cutoff, self.list)
		
		for e in filtered:
			e.flag()
				
		logging.info("Flagged {} comments for update.".format( len( filtered ) ))
		logging.debug(", ".join( map( lambda e: e.comment_id, filtered ) ) )
			
		self.sort()
		
		self.flush()
		
	def next_time(self):
		if len(self) > 0:
			return self.list[0].time
		else:
			return None
			
	def is_active(self):
		return len(self) > 0 and self.next_time() <= time.time()
			
	def process(self):
		if not self.is_active():
			return
		
		# pop the first entry
		entry = self.list.pop(0)
		
		entry.maintain()
		
		# write the updated maintenance list to file
		self.flush()
		
	def flush(self):
		with open(self.file_path, 'w') as f:
			json.dump(self.list + self.retired_list, f, cls=entry_encoder_t, sort_keys=True, indent=4)
			
		logging.debug("Saved maintenance list to file.")
			
			
			
			
			