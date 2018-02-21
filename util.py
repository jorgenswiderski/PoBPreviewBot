import urllib2
import config
import re
import time
import math
import random
from retrying import retry

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
						
def calc_deletion_check_time(comment, comment_age = None):
	if comment_age is None:
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