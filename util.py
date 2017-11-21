import urllib2
import config
import re
import time
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