# Python
import re
import traceback
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
import threading

# 3rd Party
import urllib.request, urllib.error, urllib.parse
from retrying import retry
import praw
from atomicwrites import atomic_write

from prawcore.exceptions import RequestException
from prawcore.exceptions import ServerError
from prawcore.exceptions import ResponseException
from prawcore.exceptions import Forbidden
from praw.exceptions import APIException

# Self
from config import config_helper as config

# =============================================================================

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
	logging.error("An error occurred during get_url_data(). Sleeping for {:.0f}s before retrying...".format(delay))
	return delay * 1000

def urllib_error_types(exception):
	if isinstance(exception, urllib.error.HTTPError) and exception.code == 404:
		return False
	
	return True
	
@retry(wait_exponential_multiplier=1000,
	stop_max_attempt_number=8,
	wait_func=urllib_error_retry,
	retry_on_exception=urllib_error_types)
def get_url_data(raw_url):
	# Necessary for proper response from official forums
	hdr = { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36' }

	req = urllib.request.Request(raw_url, headers=hdr)
	page = urllib.request.urlopen(req)
	
	contents = page.read()
	return contents
	
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
	
praw_errors = (RequestException, ServerError, APIException, ResponseException)
	
def is_praw_error(e):
	logging.error(e)

	if isinstance(e, praw_errors):
		logging.error("Praw error: {:s}".format(repr(e)))
		logging.error(traceback.format_exc())
		return True
	else:
		return False
	
def praw_error_retry(attempt_number, ms_since_first_attempt):
	delay = config.praw_error_wait_time * ( 2 ** ( attempt_number - 1 ) )
	logging.info("{} is sleeping for {:.0f}s...".format(threading.current_thread().name, delay))
	return delay * 1000
	
@retry(retry_on_exception=is_praw_error,
	   wait_exponential_multiplier=config.praw_error_wait_time,
	   wait_func=praw_error_retry)
def get_praw_comment_by_id(reddit, id):
	return praw.models.Comment(reddit, id=id)
		
def is_number(s):
	try:
		float(s)
		return True
	except ValueError:
		pass

	return False
	
def dump_debug_info(praw_object, exc=None, paste_key=None, xml=None, extra_data={}, dir="error", build=None):
	'''
	if not isinstance(praw_object, praw_object_wrapper_t):
		raise ValueError("dump_debug_info was passed an invalid praw_object: {}".format(type(praw_object)))
	'''
			
	if not ( paste_key is None or isinstance(paste_key, str) ):
		raise ValueError("dump_debug_info was passed an invalid paste_key: {}".format(type(paste_key)))
		
	id = praw_object.id
	
	if not os.path.exists(dir):
		os.makedirs(dir)
	
	if not os.path.exists("{}/{}".format(dir, id)):
		os.makedirs("{}/{}".format(dir, id))
		
	'''
	if xml is None and isinstance(paste_key, str):
		try:
			c = get_url_data("http://pastebin.com/raw/" + paste_key)
			c = c.replace("-", "+").replace("_", "/")
			xml = pastebin.decode_base64_and_inflate(c)
		except urllib2.URLError as e:
			logging.error("An exception occurred when attempting to fetch xml for debug dump.")
	'''
	
	if xml is not None:
		if isinstance(xml, ET.ElementTree):
			xml = xml.getroot()
		
		xml_str = ET.tostring(xml).decode()
			
		if not isinstance(xml_str, str):
			raise ValueError("dump_debug_info was passed invalid xml: is not string or coercable to string")
	
		with open("{}/{}/pastebin.xml".format(dir, id), "w") as f:
			f.write( xml_str )
			
	data = {}

	if exc is not None:
		data['error_text'] = repr(exc)
		
	if paste_key is not None:
		data['pastebin_url'] = "http://pastebin.com/raw/{}".format(paste_key)
		
	if praw_object is not None:
		if isinstance(praw_object, praw.models.Comment):
			data['type'] = "comment"
		else:
			data['type'] = "submission"
		
		data['url'] = praw_object.permalink

	if build is not None:
		if hasattr(build, 'passives_by_name'):
			data['passives'] = build.passives_by_name

			for key, val in list(data['passives'].items()):
				if not isinstance(key, str):
					logging.warning("WARNING: {} passive key overriden to 'NONE'.".format(key))
					data['passives']['NONE'] = val
					del data['passives'][key]
		
	data.update(extra_data)
	
	with atomic_write("{}/{}/info.json".format(dir, id), overwrite=True) as f:
		json.dump(data, f, sort_keys=True, indent=4)

	if exc is not None:
		with open("{}/{}/traceback.txt".format(dir, id), "w") as f:
			traceback.print_exc( file = f )
	
	logging.info("Dumped info to {}/{}/".format(dir, id))
