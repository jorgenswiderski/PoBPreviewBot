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
from output_reddit import StatException
from output_reddit import get_response_from_xml
from collections import deque
import math
import random
import traceback

locale.setlocale(locale.LC_ALL, '')

def bot_login():
	print "Logging in..."
	r = praw.Reddit(username = config.username,
		password = sconfig.password,
		client_id = sconfig.client_id,
		client_secret = sconfig.client_secret,
		user_agent = "PoBPreview")
	print "Successfully logged in."
		
	return r
	
def obj_type_str(obj):
	if isinstance(obj, praw.models.reddit.comment.Comment):
		return "comment"
	else:
		return "submission"
	
def buffered_reply(obj, response, paste_key):
	global rate_limit_timer
	if time.time() <  rate_limit_timer:
		print "Queued reply to {:s} {:s} about pastebin {:s}.".format(obj_type_str(obj), obj.id, paste_key)
		reply_queue.append((obj, response, paste_key))
		return
		
	#print "Attempting reply to " + obj.id
	try:
		log_reply(obj.reply(response), obj.id)
	except praw.exceptions.APIException as e:
		print "*** Failed to reply " + repr(e) + " ***"
		print "Buffering reply for later"
		rate_limit_timer = time.time() + 60
		reply_queue.append((obj, response))
		return
		
	print "Replied to {:s} {:s} about pastebin {:s}.".format(obj_type_str(obj), obj.id, paste_key)

	with open("{:s}s_replied_to.txt".format(obj_type_str(obj)), "a") as f:
		f.write(obj.id + "\n")

def parse_generic(comment = False, submission = False):
	if not ( comment or submission ):
		return

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
		
	comment_found_msg = False

	if "pastebin.com/" in body:
		for match in re.finditer('pastebin\.com/\w+', body):
			bin = "https://" + match.group(0)
			paste_key = pastebin.strip_url_to_key(bin)
			
			if not paste_key_is_blacklisted(paste_key):
				if not comment_found_msg:
					if comment:
						print "Found matching comment " + obj.id + "."
					elif submission:
						print "Found matching submission " + obj.id + "."
					comment_found_msg = True
				
				try:
					xml = pastebin.get_as_xml(paste_key)
				except (zlib.error, TypeError):
					print "Pastebin does not decode to XML data."
					blacklist_pastebin(paste_key)
					continue
				
				
				if xml.tag == "PathOfBuilding":
					if xml.find('Build').find('PlayerStat') is not None:
						try:
							response = get_response_from_xml(bin, xml, obj.author)
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
								f.write( "pastebin_url\t{:s}\ncomment_id\t{:s}\ncomment_url\t{:s}\nerror_text\t{:s}\ncomment_body:\n{:s}".format( bin, obj.id, obj.url, repr(e), body ))
							with open("error/" + obj.id + "/traceback.txt", "w") as f:
								traceback.print_exc( file = f )
							
							print "Dumped info to error/{:s}/".format( obj.id )
							blacklist_pastebin(paste_key)
							continue
							
						if config.username == "PoBPreviewBot" or config.subreddit != "pathofexile":
							buffered_reply(obj, response, paste_key)
							
							if isinstance(obj, praw.models.reddit.comment.Comment):
								comments_replied_to.append(obj.id)
							else:
								submissions_replied_to.append(obj.id)
						else:
							#print "Reply body:\n" + response
							with open("saved_replies.txt", "a") as f:
								f.write(response + "\n\n\n")
						
					else:
						print "XML does not contain player stats."
						blacklist_pastebin(paste_key)
				else:
					print "Pastebin does not contain Path of Building XML."
					blacklist_pastebin(paste_key)
	#else:
		#print "No pastebin found"
					
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
	return min(config.max_deletion_check_interval, max(config.min_deletion_check_interval, time.time() - comment.created_utc))
					
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
	
def parse_comments():
	num = min(get_num_entries_to_pull(comment_flow_history), config.max_pull_count)
	
	while True:
		#print "Pulling {:.0f} comments from /r/{:s}...".format(num, config.subreddit)
		
		# Grab comments
		comments = False
		
		while True:
			try:
				comments = r.subreddit(config.subreddit).comments(limit=num)
			except prawcore.exceptions.ServerError as e:
				# If server error, sleep for x then try again
				print "Praw {:s}. Sleeping for {:.0f}s...".format(repr(e), config.praw_error_wait_time)
				time.sleep(config.praw_error_wait_time)
			else:
				# If no error, break out of the loop
				break
		
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

def parse_submissions():
	num = min(get_num_entries_to_pull(submission_flow_history), config.max_pull_count)
	
	while True:
		#print "Pulling {:.0f} submissions from /r/{:s}...".format(num, config.subreddit)
		
		# Grab submissions
		submissions = False
		
		while True:
			try:
				submissions = r.subreddit(config.subreddit).new(limit=num)
			except prawcore.exceptions.ServerError as e:
				# If server error, sleep for x then try again
				print "Praw {:s}. Sleeping for {:.0f}s...".format(repr(e), config.praw_error_wait_time)
				time.sleep(config.praw_error_wait_time)
			else:
				# If no error, break out of the loop
				break
		
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
	
next_time_to_check_for_deletions = 0

def schedule_next_deletion():
	global next_time_to_check_for_deletions
	
	if len(deletion_check_list):
		next_time_to_check_for_deletions = int(deletion_check_list[0]['time'])
	else:
		next_time_to_check_for_deletions = time.time() + 1000000
		
	#print "Next deletion scheduled for " + str(next_time_to_check_for_deletions)

def check_for_deletions(t):
	#print "Checking for deletions..."

	for entry in deletion_check_list:
		if int(entry['time']) > t:
			break
		
		#print "Checking if parent comment of " + entry['id'] + " is deleted..."
		comment = praw.models.Comment(r, id=entry['id'])
		parent = comment.parent()
		if comment.is_root:
			parent._fetch()
			if parent.selftext == "[deleted]" or parent.selftext == "[removed]":
				print "Deleted comment " + comment.id + " as parent submission " + comment.parent_id + " was deleted."
				comment.delete()
				deletion_check_list.remove(entry)
		else:
			parent.refresh()
			if parent.body == "[deleted]":
				print "Deleted comment " + comment.id + " as parent comment " + comment.parent_id + " was deleted."
				comment.delete()
				deletion_check_list.remove(entry)
				
		if entry in deletion_check_list:
			delay = calc_deletion_check_time(comment) * ( 1.0 + config.deletion_check_interval_rng * ( 2.0 * random.random() - 1.0 ) )
			#print "All good, scheduled for check {:.0f}s from now.".format(delay)
			entry['time'] = t + delay
	
	# sort
	deletion_check_list.sort(key=deletion_sort)	
	
	# update file
	str = ""
	
	for entry in deletion_check_list:
		str += "{:s}\t{:.0f}\t{:s}\n".format(entry['id'], int(entry['time']), entry['parent_id'])
	
	with open("active_comments.txt", "w") as f:
		f.write( str )
	
	# schedule for the next check
	schedule_next_deletion()
		
def run_bot():
	t = time.time()
	
	if rate_limit_timer > 0 and t >= rate_limit_timer and len(reply_queue) > 0:
		t = reply_queue.pop()
		buffered_reply(t[0], t[1], t[2])
	
	if t - last_time_comments_parsed >= config.comment_parse_interval:
		parse_comments()
	if t - last_time_submissions_parsed >= config.submission_parse_interval:
		parse_submissions()
	
	if t >= next_time_to_check_for_deletions:
		check_for_deletions(t)
	
	next_update_time = min( last_time_comments_parsed + config.comment_parse_interval,
	     last_time_submissions_parsed + config.submission_parse_interval,
	     next_time_to_check_for_deletions )
		 
	if rate_limit_timer > 0:
		next_uptime_time = min(rate_limit_timer, next_update_time)
	
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