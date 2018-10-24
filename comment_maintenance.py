import time
import os
import praw
import random
import math
import urllib2
from retrying import retry

import util
import config
from response import get_response
import official_forum

from prawcore.exceptions import Forbidden
from praw.exceptions import APIException
from pob_build import EligibilityException

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
	
	def maintain(self):
		if self.comment_id not in not_author_blacklist:
			#print "[{}] Maintaining comment {:s}.".format( time.strftime("%H:%M:%S"), self.comment_id )
			
			deleted = False
			
			# Make sure the reply has not already been deleted
			if self.get_comment().body == "[deleted]":
				print "Reply {} has already been deleted, removing from list of active comments.".format(self.comment_id)
				deleted = True
			
			try:
				if not deleted:
					deleted = self.check_for_deletion()

				if not deleted:
					deleted = self.check_for_edit()
			except urllib2.HTTPError as e:
				print "An HTTPError occurred while maintaining comment {}. Skipping the check for now.".format(self.comment_id)
			except Forbidden as e:
				print "Attempted to perform forbidden action on comment {:s}. Removing from list of active comments.\n{:s}".format(self.comment_id, self.get_comment().permalink())
				# Comment may or may not be deleted, but for one reason or another we can't modify it anymore, so no point in trying to keep track of it.
				deleted = True
				
		if not deleted and time.time() - self.created_utc < config.preserve_comments_after:
			# calculate the next time we should perform maintenance on this comment
			self.update_check_time()
			
			self.last_time = time.time()
			
			# reinsert the entry at its chronologically correct place in the list
			self.list.add_entry(self)
			
	def check_for_deletion(self):
		comment = self.get_comment()
		parent = self.get_parent()
		
		if comment.is_root:
			if parent.selftext == "[deleted]" or parent.selftext == "[removed]":
				comment.delete()
				print "Deleted comment {:s} as parent submission {:s} was deleted.".format( self.comment_id, parent.id )
				
				return True
		else:
			if parent.body == "[deleted]":
				comment.delete()
				print "Deleted comment {:s} as parent comment {:s} was deleted.".format( self.comment_id, parent.id )
				
				return True
				
		return False

	@retry(retry_on_exception=util.is_praw_error,
		   wait_exponential_multiplier=config.praw_error_wait_time,
		   wait_func=util.praw_error_retry)	
	def check_for_edit(self):
		parent = self.get_parent()
		comment = self.get_comment()
		
		# has the comment been edited recently OR the comment is new (edit tag is not visible so we need to check to be safe)
		
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
					
				print "Parent {:s} no longer links to any builds, deleted response comment {:s}.".format(parent.id, self.comment_id)
				return True
			elif new_comment_body != comment.body:
				try:
					comment.edit(new_comment_body)
					print "Edited comment {:s} to reflect changes in parent {:s}.".format(self.comment_id, parent.id)
				except APIException as e:
					if "NOT_AUTHOR" in str(e):
						print "Attempted to modify comment {} that we do not own. Ignoring for the remainder of this execution.".format(self.comment_id)
						not_author_blacklist[self.comment_id] = True
					else:
						raise e
			#else:
			#	print "{:s}'s response body is unchanged.".format(parent.id)
		#else:
		#	if isinstance(parent.edited, float):
		#		print("{} was last edited {:.0f}s ago ({:.0f}s before the edit window).".format(obj_type_str(parent), t - parent.edited, self.time - 60 - parent.edited))
		#	elif t - parent.created_utc >= 400:
		#		print("{} is more than 400s old ({:.0f}s) and is not edited.".format(obj_type_str(parent), t - parent.created_utc))
				
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
				
		#print "Inserting {:s} ({:.0f}) at idx={:.0f}.".format(entry['id'], float(entry['time']), upper)
		#if lower >= 0:
		#	print float(deletion_check_list[lower]['time'])
		#if upper < len(deletion_check_list):
		#	print float(deletion_check_list[upper]['time'])
			
		self.list.insert(upper, entry)
			
	def add(self, comment):
		entry = entry_t(self, comment.id, comment.created_utc)
		
		self.add_entry( entry )
			
	def add_entry(self, entry):
		self.binary_insert( entry )
			
	def save_to_file(self):
		with open(self.file_path, "w") as f:
			f.write( '\n'.join( map( str, self.list ) ) + '\n' )
			
		#print "Saved maintenance list to file."

	def flag_for_edits(self, args):
		if not ( '-force' in args and args.index('-force') < len(args) ):
			return
		
		time_str = args[ args.index('-force') + 1 ]
		cutoff = time.time() - util.parse_time_str(time_str)
		
		filtered = filter(lambda x: x.created_utc >= cutoff, self.list)
		
		for e in filtered:
			e.flag()
				
		if len(filtered) > 0 and len(filtered) <= 10:
			print "Flagged {} comments for update:\n{}".format( len( filtered ), ", ".join( map( lambda e: e.comment_id, filtered ) ) )
		else:
			print "Flagged {} comments for update.".format( len( filtered ) )
			
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
			
			
			
			
			