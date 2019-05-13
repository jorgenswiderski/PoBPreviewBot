# Python
import time
import os
import random
import math

import datetime
import json
import logging

# 3rd Party
import praw
import urllib2from retrying import retry

from prawcore.exceptions import Forbidden
from praw.exceptions import APIException

# Self
import util
import config
from response import get_response
import official_forum

from pob_build import EligibilityException

# =============================================================================

not_author_blacklist = {};
	
class PastebinLimitException(Exception):
	pass

def write_replied_to_file(comments=False, submissions=False):
	if comments:
		with open("comments_replied_to.txt", "w") as f:
			f.write( "\n".join( comments ) + "\n" )
	if submissions:
		with open("submissions_replied_to.txt", "w") as f:
			f.write( "\n".join( submissions ) + "\n" )

class entry_t:
	def __init__(self, list, comment_id, created, time=None, last_time=None):
		self.list = list
		self.comment_id = comment_id
		self.comment = None
		self.parent = None
		self.created_utc = int(created)
		
		if time is None:
			self.update_check_time()
		else:
			self.time = int(time)
			
		if last_time is None:
			self.last_time = 0
		else:
			self.last_time = int(last_time)
		
	@classmethod
	def from_str(cls, list, str):
		split = str.strip().split('\t')
		
		return cls(list, split[0], split[2], time=split[1], last_time=split[3])
		
	def __str__(self):
		return "{:s}\t{:.0f}\t{:.0f}\t{:.0f}".format(self.comment_id, self.time, self.created_utc, self.last_time)
			
	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)
	def get_comment(self):
		if self.comment is None:
			self.comment = util.get_praw_comment_by_id(self.list.reddit, self.comment_id)
		
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
		
	def update_check_time(self):
		t = time.time()
		comment_age = t - self.created_utc
		self.time = t + entry_t.get_check_time(comment_age)
		
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
			util.tprint("ClientException occurred when refreshing for maintenance of comment {}".format(self.comment_id))
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
					util.tprint("Reply {} has already been deleted, removing from list of active comments.".format(self.comment_id))
					deleted = True
				
				try:
					if not deleted:
						deleted = self.check_for_deletion()

					if not deleted:
						deleted = self.check_for_edit()
				except urllib2.HTTPError as e:
					util.tprint("An HTTPError occurred while maintaining comment {}. Skipping the check for now.".format(self.comment_id))
				except Forbidden as e:
					util.tprint("Attempted to perform forbidden action on comment {:s}. Removing from list of active comments.\n{:s}".format(self.comment_id, self.get_comment().permalink()))
					# Comment may or may not be deleted, but for one reason or another we can't modify it anymore, so no point in trying to keep track of it.
					deleted = True
			else:
				failure = True
				
		if not deleted and time.time() - self.created_utc < config.preserve_comments_after:
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
			
	def check_for_deletion(self):
		comment = self.get_comment()
		parent = self.get_parent()
		
		if comment.is_root:
			if parent.selftext == "[deleted]" or parent.selftext == "[removed]":
				comment.delete()
				util.tprint("Deleted comment {:s} as parent submission {:s} was deleted.".format( self.comment_id, parent.id ))
				
				return True
		else:
			if parent.body == "[deleted]":
				comment.delete()
				util.tprint("Deleted comment {:s} as parent comment {:s} was deleted.".format( self.comment_id, parent.id ))
				
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
				if isinstance(parent, praw.models.Comment):
					new_comment_body = get_response(self.list.reddit, parent, parent.body)
				else:
					new_comment_body = get_response(self.list.reddit, parent, util.get_submission_body( parent ), author = util.get_submission_author( parent ) )
			except (EligibilityException, PastebinLimitException) as e:
				print(e)
			
			if new_comment_body is None:
				comment.delete()
				
				if isinstance(parent, praw.models.Comment):
					if parent.id in self.list.comments_replied_to:
						self.list.comments_replied_to.remove(parent.id)
						write_replied_to_file(comments=self.list.comments_replied_to)
				else:
					if parent.id in self.list.submissions_replied_to:
						self.list.submissions_replied_to.remove(parent.id)
						write_replied_to_file(submissions=self.list.submissions_replied_to)
					
				util.tprint("Parent {:s} no longer links to any builds, deleted response comment {:s}.".format(parent.id, self.comment_id))
				return True
			elif new_comment_body != comment.body:
				try:
					comment.edit(new_comment_body)
					util.tprint("Edited comment {:s} to reflect changes in parent {:s}.".format(self.comment_id, parent.id))
				except APIException as e:
					if "NOT_AUTHOR" in str(e):
						util.tprint("Attempted to modify comment {} that we do not own. Ignoring for the remainder of this execution.".format(self.comment_id))
						not_author_blacklist[self.comment_id] = True
					else:
						raise e
		'''
			else:
				util.tprint("{:s}'s response body is unchanged.".format(parent.id))
		else:
			if isinstance(parent.edited, float):
				time_since_edit = math.ceil(time.time() - parent.edited)
				seconds_before_cutoff = math.ceil(self.time - 60 - parent.edited)
				util.tprint("{} was last edited [{}] ago ([{}] before the edit window).".format(util.obj_type_str(parent), datetime.timedelta(seconds=time_since_edit), datetime.timedelta(seconds=seconds_before_cutoff)))
			elif time.time() - parent.created_utc >= 400:
				age = math.ceil(time.time() - parent.created_utc)
				util.tprint("{} is more than 400s old [{}] and is not edited.".format(util.obj_type_str(parent), str(datetime.timedelta(seconds=age))))
		'''		
				
		return False
		
class maintain_list_t:
	def __init__(self, file_path, reddit, comments, submissions):
		self.file_path = file_path
		self.reddit = reddit
		self.comments_replied_to = comments
		self.submissions_replied_to = submissions
		
		self.list = []
		
		if not os.path.isfile(file_path):
			self.list = []
		else:
			self.__init_from_file__()
			self.sort()
			
	def __init_from_file__(self):
		with open(self.file_path, 'r') as f:
			buf = f.read()
			buf = buf.split('\n')
			buf = filter(None, buf)
			
			for line in buf:
				self.list.append( entry_t.from_str( self, line ) )
				
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
				
		logging.debug("Inserting {:s} ({:.0f}) {} at idx={:.0f}.".format(entry['id'], float(entry['time']), self, upper))
		#if lower >= 0:
		#	util.tprint(float(deletion_check_list[lower]['time']))
		#if upper < len(deletion_check_list):
		#	util.tprint(float(deletion_check_list[upper]['time']))
			
		self.list.insert(upper, entry)
			
	def add(self, comment):
		entry = entry_t(self, comment.id, comment.created_utc)
		
		self.add_entry( entry )
			
	def add_entry(self, entry):
		self.binary_insert( entry )
			
	def save_to_file(self):
		with open(self.file_path, "w") as f:
			f.write( '\n'.join( map( str, self.list ) ) + '\n' )
			
		logging.debug("Saved maintenance list to file.")

	def flag_for_edits(self, args):
		if not ( '-force' in args and args.index('-force') < len(args) ):
			return
		
		time_str = args[ args.index('-force') + 1 ]
		cutoff = time.time() - util.parse_time_str(time_str)
		
		filtered = filter(lambda x: x.created_utc >= cutoff, self.list)
		
		for e in filtered:
			e.flag()
				
		if len(filtered) > 0 and len(filtered) <= 10:
			util.tprint("Flagged {} comments for update:\n{}".format( len( filtered ), ", ".join( map( lambda e: e.comment_id, filtered ) ) ))
		else:
			util.tprint("Flagged {} comments for update.".format( len( filtered ) ))
			
		self.sort()
		
		self.save_to_file()
		
	def next_time(self):
		if len(self) > 0:
			return self.list[0].time
		else:
			return None
			
	def process(self):
		if not ( len(self) > 0 and self.next_time() <= time.time() ):
			return
		
		# pop the first entry
		entry = self.list.pop(0)
		
		entry.maintain()
		
		# write the updated maintenance list to file
		self.save_to_file()
			
			
			
			
			