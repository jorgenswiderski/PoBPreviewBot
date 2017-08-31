import praw
import live_config as config
import live_secret_config as sconfig
#import config
#import secret_config as sconfig
import time
import os
import re
import defusedxml.ElementTree as ET
import locale
import pastebin
import zlib
from pob_build import StatException
from pob_build import pob_build
from pob_build import UnsupportedException
from collections import deque
import math
import random
import traceback
import urllib2
from retrying import retry

from prawcore.exceptions import RequestException
from prawcore.exceptions import ServerError
from prawcore.exceptions import ResponseException
from prawcore.exceptions import Forbidden
from praw.exceptions import APIException


BOT_FOOTER = "[^Path ^of ^Building](https://github.com/Openarl/PathOfBuilding) ^| ^This ^reply ^will ^be ^automatically ^removed ^if ^its ^parent ^comment ^is ^deleted. ^| ^[Feedback?](https://www.reddit.com/r/PoBPreviewBot/)"

locale.setlocale(locale.LC_ALL, '')

def bot_login():
	print "Logging in..."
	r = praw.Reddit(username = config.username,
		password = sconfig.password,
		client_id = sconfig.client_id,
		client_secret = sconfig.client_secret,
		user_agent = "linux:PoBPreviewBot:v1.0 (by /u/aggixx)")
	print "Successfully logged in as {:s}.".format(config.username)
		
	return r
	
	
praw_errors = (RequestException, ServerError, APIException, ResponseException)

def is_praw_error(e):
	print e
	if isinstance(e, praw_errors):
		print "Praw error: {:s}".format(repr(e))
		return True
	else:
		return False
	
def praw_error_retry(attempt_number, ms_since_first_attempt):
	delay = config.praw_error_wait_time * ( 2 ** ( attempt_number - 1 ) )
	print "Sleeping for {:.0f}s...".format(delay)
	return delay * 1000
	
def obj_type_str(obj):
	if isinstance(obj, praw.models.reddit.comment.Comment):
		return "comment"
	else:
		return "submission"
	
def buffered_reply(obj, response):
	global rate_limit_timer
	if time.time() <  rate_limit_timer:
		print "Queued reply to {:s} {:s}.".format(obj_type_str(obj), obj.id)
		reply_queue.append((obj, response))
		return
		
	#print "Attempting reply to " + obj.id
	try:
		log_reply(obj.reply(response), obj.id)
	except APIException as e:
		print "*** Failed to reply " + repr(e) + " ***"
		print "Buffering reply for later"
		rate_limit_timer = time.time() + 60
		reply_queue.append((obj, response))
		return
		
	print "Replied to {:s} {:s}.".format(obj_type_str(obj), obj.id)

	with open("{:s}s_replied_to.txt".format(obj_type_str(obj)), "a") as f:
		f.write(obj.id + "\n")

def get_response(comment = False, submission = False):
	if not ( comment or submission ):
		raise Exception("get_response passed no parameters")

	obj = ""
	body = ""
	if comment:
		obj = comment
		body = comment.body
	elif submission:
		obj = submission
		if submission.selftext == '':
			body = submission.url
		else:
			body = submission.selftext
	
	#print "Processing " + obj.id
		
	if obj.author == r.user.me():
		#print "Author is self, ignoring"
		return

	if "pastebin.com/" in body:
		responses = {}
	
		for match in re.finditer('pastebin\.com/\w+', body):
			bin = "https://" + match.group(0)
			paste_key = pastebin.strip_url_to_key(bin)
			
			if not paste_key_is_blacklisted(paste_key) and paste_key not in responses:
				try:
					xml = pastebin.get_as_xml(paste_key)
				except (zlib.error, TypeError):
					print "Pastebin does not decode to XML data."
					blacklist_pastebin(paste_key)
					continue
				except urllib2.HTTPError as e:
					print "urllib2 {:s}".format(repr(e))
					blacklist_pastebin(paste_key)
					continue
				
				if xml.tag == "PathOfBuilding":
					if xml.find('Build').find('PlayerStat') is not None:
						try:
							build = pob_build(xml, bin, obj.author)
							response = build.get_response()
						except UnsupportedException as e:
							print "{:s}: {:s}".format(obj.id, repr(e))
							blacklist_pastebin(paste_key)
							continue
						except Exception as e:
							print repr(e)
						
							# dump xml for debugging later
							c = pastebin.get_contents(paste_key)
							c = c.replace("-", "+").replace("_", "/")
							
							if not os.path.exists("error/" + obj.id):
								os.makedirs("error/" + obj.id)
							
							with open("error/" + obj.id + "/pastebin.xml", "w") as f:
								f.write( pastebin.decode_base64_and_inflate(c) )
							with open("error/" + obj.id + "/info.txt", "w") as f:
								f.write( "pastebin_url\t{:s}\ncomment_id\t{:s}\ncomment_url\t{:s}\nerror_text\t{:s}".format( bin, obj.id, obj.permalink, repr(e) ))
							with open("error/" + obj.id + "/traceback.txt", "w") as f:
								traceback.print_exc( file = f )
							
							print "Dumped info to error/{:s}/".format( obj.id )
							blacklist_pastebin(paste_key)
							continue
							
						responses[paste_key] = response
					else:
						print "XML does not contain player stats."
						blacklist_pastebin(paste_key)
				else:
					print "Pastebin does not contain Path of Building XML."
					blacklist_pastebin(paste_key)
		
		
		if len(responses) > 0 and len(responses) <= 10:
			comment_body = ""
			if len(responses) > 1:
				for res in responses:
					if comment_body != "":
						comment_body += "\n\n[](#quote_break)  \n"
					comment_body += '>' + responses[res].replace('\n', "\n>")
			else:
				for res in responses:
					comment_body = responses[res] + "  \n*****"
				
			comment_body += '\n\n' + BOT_FOOTER
			
			return comment_body
			
def parse_generic( comment = False, submission = False ):
	# get response text
	response = get_response( comment = comment, submission = submission )
	
	if not response:
		return
		
	if comment:
		print "Found matching comment " + comment.id + "."
	elif submission:
		print "Found matching submission " + submission.id + "."
	
	# post reply
	if config.username == "PoBPreviewBot" or config.subreddit != "pathofexile":
		buffered_reply(comment or submission, response)
		
		if comment:
			comments_replied_to.append(comment.id)
		elif submission:
			submissions_replied_to.append(submission.id)
		else:
			raise Exception('parse_generic was passed neither a comment nor submission.')
	else:
		#print "Reply body:\n" + response
		with open("saved_replies.txt", "a") as f:
			f.write(response + "\n\n\n")
					
def deletion_sort(a):
	return a['time']
					
def get_deletion_check_list():
	cl = []
	
	if not os.path.isfile("active_comments.txt"):
		cl = []
	else:
		with open("active_comments.txt", "r") as f:
			buf = f.read()
			buf = buf.split("\n")
			buf = filter(None, buf)
			for line in buf:
				s = line.split("\t")
				cl.append( {
					'id': s[0],
					'time': s[1],
					'parent_id': s[2],
				} )
			cl.sort(key=deletion_sort)
			
	return cl
	
					
def calc_deletion_check_time(comment):
	comment_age = time.time() - comment.created_utc
	
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
		t *= math.pow( 2, ( comment_age - 604800 ) / 604800 )
		
	if config.deletion_check_interval_rng > 0:
		t *= 1.0 + config.deletion_check_interval_rng * ( 2.0 * random.random() - 1.0 )
		
	return t
		
					
def log_reply(comment, parent):
	check_time = time.time() + calc_deletion_check_time(comment)
	str = "{:s}\t{:.0f}\t{:s}\n".format(comment.id, check_time, parent)
	
	i = 0
	
	for entry in deletion_check_list:
		if check_time < entry['time']:
			break
		i += 1
	
	deletion_check_list.insert(i, {
		'id': comment.id,
		'time': check_time,
		'parent_id': parent,
	} )
	
	if i == 0:
		schedule_next_deletion()
	
	with open("active_comments.txt", "a") as f:
		f.write(str)
	
def track_comment(comment):
	if len(processed_comments_list) >= 250:
		del processed_comments_dict[processed_comments_list[0]]
		processed_comments_list.pop(0) 
	
	processed_comments_list.append(comment.id)
	processed_comments_dict[comment.id] = True
	global num_new_comments
	num_new_comments += 1
	
def track_submission(submission):
	if len(processed_submissions_list) >= 250:
		del processed_submissions_dict[processed_submissions_list[0]]
		processed_submissions_list.pop(0) 
	
	processed_submissions_list.append(submission.id)
	processed_submissions_dict[submission.id] = True
	global num_new_submissions
	num_new_submissions += 1

def save_comment_count():
	if len(comment_flow_history) >= config.pull_count_tracking_window:
		comment_flow_history.pop(0)
		
	global num_new_comments
	comment_flow_history.append(num_new_comments)
	num_new_comments = 0
	#print comment_flow_history

def save_submission_count():
	if len(submission_flow_history) >= config.pull_count_tracking_window:
		submission_flow_history.pop(0)
	
	global num_new_submissions
	submission_flow_history.append(num_new_submissions)
	num_new_submissions = 0
	#print submission_flow_history
	
def get_num_entries_to_pull(history):
	if len(history) == 0:
		return config.initial_pull_count
		
	return math.floor(max( max(history), config.min_pull_count ))
	
last_time_comments_parsed = 0
	
@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)
def parse_comments():
	num = min(get_num_entries_to_pull(comment_flow_history), config.max_pull_count)
	
	while True:
		#print "Pulling {:.0f} comments from /r/{:s}...".format(num, config.subreddit)
		
		# Grab comments
		comments = r.subreddit(config.subreddit).comments(limit=num)
		
		for comment in comments:
			if comment.id not in processed_comments_dict:
				track_comment(comment)
				if comment.id not in comments_replied_to:
					parse_generic( comment = comment )
					
		if num_new_comments < num or num >= config.max_pull_count:
			break
		elif len(comment_flow_history) > 0:
			num *= 2
		else:
			break
			
	global last_time_comments_parsed
	last_time_comments_parsed = time.time()
	
	save_comment_count()
	
last_time_submissions_parsed = 0

@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)
def parse_submissions():
	num = min(get_num_entries_to_pull(submission_flow_history), config.max_pull_count)
	
	while True:
		#print "Pulling {:.0f} submissions from /r/{:s}...".format(num, config.subreddit)
		
		# Grab submissions
		submissions = r.subreddit(config.subreddit).new(limit=num)
		
		for submission in submissions:
			if submission.id not in processed_submissions_dict:
				track_submission(submission)
				if submission.id not in submissions_replied_to:
					parse_generic( submission = submission ) 
		
		if num_new_submissions < num or num >= config.max_pull_count:
			break
		elif len(submission_flow_history) > 0:
			num *= 2
		else:
			break
			
	global last_time_submissions_parsed
	last_time_submissions_parsed = time.time()
	
	save_submission_count()
	
next_time_to_maintain_comments = 0

def schedule_next_deletion():
	global next_time_to_maintain_comments
	
	if len(deletion_check_list):
		next_time_to_maintain_comments = int(deletion_check_list[0]['time'])
	else:
		next_time_to_maintain_comments = time.time() + 1000000
		
	#print "Next deletion scheduled for " + str(next_time_to_maintain_comments)

@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)
def check_comment_for_deletion(parent, comment):
	if comment.is_root:
		if parent.selftext == "[deleted]" or parent.selftext == "[removed]":
			comment.delete()
			print "Deleted comment {:s} as parent submission {:s} was deleted.".format( comment.id, comment.parent_id )
			
			return True
	else:
		if parent.body == "[deleted]":
			comment.delete()
			print "Deleted comment {:s} as parent comment {:s} was deleted.".format( comment.id, comment.parent_id )
			
			return True
			
	return False

@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)	
def check_comment_for_edit(t, parent, comment):
	# has the comment been edited recently OR the comment is new (edit tag is not visible so we need to check to be safe)
	
	if ( isinstance(parent.edited, float) and parent.edited >= t - calc_deletion_check_time(comment) ) or t - parent.created_utc < 400:
		new_comment_body = None
		
		if comment.is_root:
			new_comment_body = get_response(submission = parent)
		else:
			new_comment_body = get_response(comment = parent)
		
		if not new_comment_body:
			comment.delete()
			print "Parent {:s} no longer links to any builds, deleted response comment {:s}.".format(parent.id, comment.id)
			return True
		elif new_comment_body != comment.body:
			comment.edit(new_comment_body)
			print "Edited comment {:s} to reflect changes in parent {:s}.".format(comment.id, parent.id)
		#else:
		#	print "{:s}'s response body is unchanged.".format(parent.id)
			
	return False
			
def write_maintenance_list_to_file():
	str = ""
	
	for entry in deletion_check_list:
		str += "{:s}\t{:.0f}\t{:s}\n".format(entry['id'], int(entry['time']), entry['parent_id'])
	
	with open("active_comments.txt", "w") as f:
		f.write( str )
		
def maintenance_list_insert(entry):
	# binary search for the index to insert at
	
	# define search boundaries
	lower = -1
	upper = len(deletion_check_list)
	
	# while our boundaries have not crossed
	while abs( lower - upper ) > 1:
		# take the average
		middle = int( math.floor( ( lower + upper ) / 2  ) )
		
		# move the upper or lower boundary to halve the search space
		if int(deletion_check_list[middle]['time']) > int(entry['time']):
			upper = middle
		else:
			lower = middle
			
	#print "Inserting {:s} ({:.0f}) at idx={:.0f}.".format(entry['id'], float(entry['time']), upper)
	#if lower >= 0:
	#	print float(deletion_check_list[lower]['time'])
	#if upper < len(deletion_check_list):
	#	print float(deletion_check_list[upper]['time'])
		
	deletion_check_list.insert(upper, entry)
	
@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)
def get_praw_comment_by_id(id):
	return praw.models.Comment(r, id=id)
	
@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)	
def get_praw_comment_parent(comment):
	return comment.parent()
	
def maintain_comments(t):
	# confirm that there are any comments that need to be checked
	if int(deletion_check_list[0]['time']) > t:
		return
	
	# pop the first entry
	entry = deletion_check_list.pop(0)
	
	#print "Maintaining comment {:s}.".format(entry['id'])
	
	# create a comment object from the id in the entry
	comment = get_praw_comment_by_id(entry['id'])
	parent = get_praw_comment_parent(comment)
	
	try:
		deleted = check_comment_for_deletion(parent, comment)

		if not deleted:
			deleted = check_comment_for_edit(t, parent, comment)
	except Forbidden as e:
		print "Attempted to perform forbidden action on comment {:s}. Removing from list of active comments.\n{:s}".format(comment.id, comment.permalink())
		# Comment may or may not be deleted, but for one reason or another we can't modify it anymore, so no point in trying to keep track of it.
		deleted = True
			
	if not deleted and t - comment.created_utc < config.preserve_comments_after:
		# calculate the next time we should perform maintenance on this comment
		entry['time'] = t + calc_deletion_check_time(comment)
		
		# reinsert the entry at its chronologically correct place in the list
		maintenance_list_insert(entry)
	
	# write the updated maintenance list to file
	write_maintenance_list_to_file()
	
	# schedule for the next check
	schedule_next_deletion()
		
def run_bot():
	t = time.time()
	
	if rate_limit_timer > 0 and t >= rate_limit_timer and len(reply_queue) > 0:
		rep = reply_queue.pop()
		buffered_reply(rep[0], rep[1])
	
	if t - last_time_comments_parsed >= config.comment_parse_interval:
		parse_comments()
		
	if t - last_time_submissions_parsed >= config.submission_parse_interval:
		parse_submissions()
	
	if t >= next_time_to_maintain_comments:
		maintain_comments(t)
	
	next_update_time = min( last_time_comments_parsed + config.comment_parse_interval,
	     last_time_submissions_parsed + config.submission_parse_interval,
	     next_time_to_maintain_comments )
		 
	if rate_limit_timer > 0:
		next_update_time = min(rate_limit_timer, next_update_time)
	
	if next_update_time > t:
		#print "Sleeping for {:n}s...".format(next_update_time - t)
		time.sleep( next_update_time - t )
			
			
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
	
def blacklist_pastebin(paste_key):
	if paste_key in pastebin_blacklist:
		return
	
	pastebin_blacklist[paste_key] = True

	with open("pastebin_blacklist.txt", "a") as f:
		f.write(paste_key + "\n")
		
	print "Blacklisted paste key " + paste_key + "."
		
def get_blacklisted_pastebins():
	pastebin_blacklist = {}
	
	if os.path.isfile("pastebin_blacklist.txt"):
		dupe = False
	
		with open("pastebin_blacklist.txt", "r") as f:
			list = f.read()
			list = list.split("\n")
			list = filter(None, list)
			
			for entry in list:
				if entry in pastebin_blacklist:
					dupe = True
					
				pastebin_blacklist[entry] = True
				
		# if the list contained duplicates, write
		# back to the file with the duplicates removed
		if dupe:
			print "Deduplicating pastebin blacklist."
			with open("pastebin_blacklist.txt", "w") as f:
				list = []
				
				for k in pastebin_blacklist:
					list.append(k)
					
				f.write( ( '\n'.join(list) ) + '\n' )
		
	return pastebin_blacklist
	
def paste_key_is_blacklisted(paste_key):
	return paste_key in pastebin_blacklist

	
r = bot_login()
comments_replied_to = get_saved_comments()
#print comments_replied_to
submissions_replied_to = get_saved_submissions()
#print submissions_replied_to
pastebin_blacklist = get_blacklisted_pastebins()
#print pastebin_blacklist
deletion_check_list = get_deletion_check_list()
schedule_next_deletion()
#print deletion_check_list

rate_limit_timer = 0

reply_queue = deque()

processed_comments_list = []
processed_comments_dict = {}
processed_submissions_list = []
processed_submissions_dict = {}
num_new_comments = 0
num_new_submissions = 0
comment_flow_history = []
submission_flow_history = []

print "Scanning /r/" + config.subreddit + "..."

while True:
	run_bot()