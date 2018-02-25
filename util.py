import urllib2
import config
import re
from retrying import retry
import praw

import official_forum

from prawcore.exceptions import RequestException
from prawcore.exceptions import ServerError
from prawcore.exceptions import ResponseException
from prawcore.exceptions import Forbidden
from praw.exceptions import APIException

def floatToSigFig(n):
	negative = False
	if n < 0:
		negative = True
	
	n = abs(n)
	
	s = ""
	
	if n <= 1e3:
		s = "{:.0f}".format(n)
	elif n <= 1e6:
		s = "{:.3g}k".format(n/1e3)
	elif n <= 1e9:
		s = "{:.3g}m".format(n/1e6)
	elif n <= 1e12:
		s = "{:.3g}b".format(n/1e9)
	else:
		s = "{:.0f}".format(n)
		
	if negative:
		s = '-' + s

	return s
	
def urllib_error_retry(attempt_number, ms_since_first_attempt):
	delay = 1 * ( 2 ** ( attempt_number - 1 ) )
	print "An error occurred during get_url_data(). Sleeping for {:.0f}s before retrying...".format(delay)
	return delay * 1000
	
@retry(wait_exponential_multiplier=1000,
	stop_max_attempt_number=8,
	wait_func=urllib_error_retry)
def get_url_data(raw_url):
	url = urllib2.urlopen(raw_url)
	
	data = url.read()
	return data
	
def parse_time_str(str):
	if "d" in str:
		mo = re.match("(\d+)d(\d+)h(\d+)m", str)
		return ( ( int(mo.group(1)) * 24 + int(mo.group(2)) ) * 60 + int(mo.group(3)) ) * 60
	elif "h" in str:
		mo = re.match("(\d+)h(\d+)m", str)
		return ( int(mo.group(1)) * 60 + int(mo.group(2)) ) * 60
	elif "m" in str:
		mo = re.match("(\d+)m", str)
		return int(mo.group(1)) * 60
	else:
		raise Exception("time_str did not follow XdXhXm format.")
	
def obj_type_str(obj):
	if isinstance(obj, praw.models.Comment):
		return "comment"
	else:
		return "submission"	
		
def praw_obj_str(obj):
	return "{} {}".format(obj_type_str(obj), obj.id)
	
praw_errors = (RequestException, ServerError, APIException, ResponseException)
	
def is_praw_error(e):
	print e
	if isinstance(e, praw_errors):
		print "Praw error: {:s}".format(repr(e))
		print traceback.format_exc()
		return True
	else:
		return False
	
def praw_error_retry(attempt_number, ms_since_first_attempt):
	delay = config.praw_error_wait_time * ( 2 ** ( attempt_number - 1 ) )
	print "Sleeping for {:.0f}s...".format(delay)
	return delay * 1000
	
@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)
def get_praw_comment_by_id(reddit, id):
	return praw.models.Comment(reddit, id=id)
	
def get_submission_body( submission ):
	if submission.selftext == '':
		if official_forum.is_post( submission.url ):
			return official_forum.get_op_body( submission.url )
		else:
			return submission.url
	else:
		return submission.selftext 
		
def get_submission_author( submission ):
	if submission.selftext == '' and official_forum.is_post( submission.url ):
		return official_forum.get_op_author( submission.url )
	else:
		return submission.author
		
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass
 
	'''
    try:
        import unicodedata
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass
	'''
 
	return False