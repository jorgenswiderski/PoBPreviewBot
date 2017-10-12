import urllib2
import config
import re

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
	
	
	
def get_url_data(raw_url):
	url = False
	
	while True:
		try:
			url = urllib2.urlopen(raw_url)
		except urllib2.HTTPError as e:
			if "HTTP Error" not in repr(e):
				raise e
				
			print "urllib2 failed to pull {:s}: {:s}. Sleeping for {:.0f}s...".format(raw_url, repr(e), config.urllib_error_wait_time)
			time.sleep(config.urllib_error_wait_time)
		else:
			# If no error, break out of the loop
			break
	
	data = url.read()
	return data