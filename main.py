import praw
import time
import os
import re
import defusedxml.ElementTree as ET
import locale
from collections import deque
import math
import random
from retrying import retry
import sys

#import live_config as config
#import live_secret_config as sconfig
import config
import secret_config as sconfig
import pastebin
import util
import status
from util import obj_type_str
from comment_maintenance import maintain_list_t
from reply_buffer import reply_handler_t
from response import get_response

from pob_build import EligibilityException
from comment_maintenance import PastebinLimitException

locale.setlocale(locale.LC_ALL, '')

file("bot.pid", 'w').write(str(os.getpid()))

def bot_login():
	util.tprint("Logging in...")
	r = praw.Reddit(username = config.username,
		password = sconfig.password,
		client_id = sconfig.client_id,
		client_secret = sconfig.client_secret,
		user_agent = "linux:PoBPreviewBot:v1.0 (by /u/aggixx)")
	util.tprint("Successfully logged in as {:s}.".format(config.username))
		
	return r
			
def parse_generic( reply_object, body, author = None ):
	if not ( reply_object and ( isinstance( reply_object, praw.models.Comment ) or isinstance( reply_object, praw.models.Submission ) ) ):
		raise ValueError("parse_generic passed invalid reply_object")
	elif not ( body and ( isinstance( body, str ) or isinstance( body, unicode ) ) ):
		# dump xml for debugging later
		exc = ValueError("parse_generic passed invalid body")
		util.dump_debug_info(reply_object, exc=exc, extra_data={
			'body_type': type(body),
			'body': body
		})
		blacklist_pastebin(paste_key)
		raise exc
	
	response = None
	
	try:
		# get response text
		response = get_response( r, reply_object, body, author = author )
	except (EligibilityException, PastebinLimitException) as e:
		print(str(e))
		
	if response is None:
		return False
		
	util.tprint("Found matching {:s} {:s}.".format(obj_type_str(reply_object), reply_object.id))
	
	# post reply
	if config.username == "PoBPreviewBot" or "pathofexile" not in config.subreddits:
		reply_queue.reply(reply_object, response)
	else:
		#util.tprint("Reply body:\n" + response)
		with open("saved_replies.txt", "a") as f:
			f.write(response + "\n\n\n")
			
	return True
		
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

def save_comment_count(subreddit):
	if len(comment_flow_history[subreddit]) >= config.pull_count_tracking_window:
		comment_flow_history[subreddit].pop(0)
		
	global num_new_comments
	comment_flow_history[subreddit].append(num_new_comments)
	num_new_comments = 0
	#util.tprint(comment_flow_history[subreddit])

def save_submission_count(subreddit):
	if len(submission_flow_history[subreddit]) >= config.pull_count_tracking_window:
		submission_flow_history[subreddit].pop(0)
	
	global num_new_submissions
	submission_flow_history[subreddit].append(num_new_submissions)
	num_new_submissions = 0
	#util.tprint(submission_flow_history[subreddit])
	
def get_num_entries_to_pull(history):
	if len(history) == 0:
		return config.initial_pull_count
		
	return math.floor(min(max( max(history), config.min_pull_count ), config.max_pull_count))
	
def reply_to_summon(comment):
	errs = []
	parent = comment.parent()
	
	if parent.author == r.user.me():
		return
		
	p_response = None
	
	try:
		if isinstance(parent, praw.models.Comment):
			p_response = get_response(r, parent, parent.body, ignore_blacklist = True)
		else:
			p_response = get_response(r, parent, util.get_submission_body( parent ), author = util.get_submission_author( parent ), ignore_blacklist = True)
	except (EligibilityException, PastebinLimitException) as e:
		errs.append("* {}".format(str(e)))
	
	response = None
		
	if p_response is not None and parent.id not in comments_replied_to and parent.id not in submissions_replied_to and not reply_queue.contains_id(parent.id):
		if config.username == "PoBPreviewBot" or "pathofexile" not in config.subreddits:
			reply_queue.reply(parent, p_response)
		response = "Seems like I missed comment {}! I've replied to it now, sorry about that.".format(parent.id)
	elif len(errs) > 0:
		response = "The {} {} was not responded to for the following reason{}:\n\n{}".format(obj_type_str(parent), parent.id, "s" if len(errs) > 1 else "", "  \n".join(errs))
	else:
		response = config.BOT_INTRO
	
	if response is None:
		return
	
	if config.username == "PoBPreviewBot" or "pathofexile" not in config.subreddits:
		reply_queue.reply(comment, response, log = False)
	
last_time_comments_parsed = {}
for sub in config.subreddits:
	last_time_comments_parsed[sub] = 0
	
@retry(retry_on_exception=util.is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=util.praw_error_retry)
def parse_comments(subreddit):
	num = get_num_entries_to_pull(comment_flow_history[subreddit])
	
	while True:
		#util.tprint("Pulling {:.0f} comments from /r/{:s}...".format(num, subreddit))
		
		# Grab comments
		comments = r.subreddit(subreddit).comments(limit=num)
		
		for comment in comments:
			if comment.id not in processed_comments_dict:
				track_comment(comment)
				if comment.id not in comments_replied_to and not reply_queue.contains_id(comment.id):
					replied = parse_generic( comment, comment.body )
					
					if not replied and ( "u/" + config.username ).lower() in comment.body.lower():
						reply_to_summon( comment )
					
		if num_new_comments < num or num >= config.max_pull_count:
			break
		elif len(comment_flow_history[subreddit]) > 0:
			num *= 2
		else:
			break
			
	global last_time_comments_parsed
	last_time_comments_parsed[subreddit] = time.time()
	
	save_comment_count(subreddit)
	
last_time_submissions_parsed = {}
for sub in config.subreddits:
	last_time_submissions_parsed[sub] = 0

@retry(retry_on_exception=util.is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=util.praw_error_retry)
def parse_submissions(subreddit):
	num = get_num_entries_to_pull(submission_flow_history[subreddit])
	
	while True:
		#util.tprint("Pulling {:.0f} submissions from /r/{:s}...".format(num, subreddit))
		
		# Grab submissions
		submissions = r.subreddit(subreddit).new(limit=num)
		
		for submission in submissions:
			if submission.id not in processed_submissions_dict:
				track_submission(submission)
				if submission.id not in submissions_replied_to and not reply_queue.contains_id(submission.id):
					parse_generic( submission, util.get_submission_body( submission ), author = util.get_submission_author( submission ) )
		
		if num_new_submissions < num or num >= config.max_pull_count:
			break
		elif len(submission_flow_history[subreddit]) > 0:
			num *= 2
		else:
			break
			
	global last_time_submissions_parsed
	last_time_submissions_parsed[subreddit] = time.time()
	
	save_submission_count(subreddit)
			
def get_sleep_time():
	next_update_time = 10000000000
	
	if len(maintain_list) > 0:
		next_update_time = min(next_update_time, maintain_list.next_time())
		 
	for sub in config.subreddits:
		next_update_time = min( next_update_time,
		last_time_comments_parsed[sub] + config.comment_parse_interval,
		last_time_submissions_parsed[sub] + config.submission_parse_interval )
		 
	if len(reply_queue) > 0:
		next_update_time = min( next_update_time, reply_queue.throttled_until() )
	
	return next_update_time - time.time()
		
def run_bot():
	reply_queue.process()
	
	t = time.time()
	
	for sub in config.subreddits:
		if t - last_time_comments_parsed[sub] >= config.comment_parse_interval:
			#util.tprint("[{}] Reading comments from /r/{}".format(time.strftime("%H:%M:%S"), sub))
			parse_comments(sub)
	
	for sub in config.subreddits:
		if t - last_time_submissions_parsed[sub] >= config.submission_parse_interval:
			#util.tprint("[{}] Reading submissions from /r/{}".format(time.strftime("%H:%M:%S"), sub))
			parse_submissions(sub)
	
	maintain_list.process()
	
	status.update()
		
	# calculate the next time we need to do something
	st = get_sleep_time()
	
	if st > 0:
		#util.tprint("[{}] Sleeping for {:.2f}s...".format( time.strftime("%H:%M:%S"), st ))
		time.sleep( st )
			
			
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
	
	
r = bot_login()
comments_replied_to = get_saved_comments()
#util.tprint(comments_replied_to)
submissions_replied_to = get_saved_submissions()
#util.tprint(submissions_replied_to)
maintain_list = maintain_list_t( "active_comments.txt", r, comments_replied_to, submissions_replied_to )
	
if '-force' in sys.argv:
	maintain_list.flag_for_edits(sys.argv)

reply_queue = reply_handler_t( maintain_list )

processed_comments_list = []
processed_comments_dict = {}
processed_submissions_list = []
processed_submissions_dict = {}
num_new_comments = 0
num_new_submissions = 0

comment_flow_history = {}
submission_flow_history = {}

for sub in config.subreddits:
	comment_flow_history[sub] = []
	submission_flow_history[sub] = []

util.tprint("Scanning subreddits " + repr(config.subreddits) + "...")

while True:
	run_bot()