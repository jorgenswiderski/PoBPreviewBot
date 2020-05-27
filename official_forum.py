# Python
import re
import time
import logging

# 3rd Party
import urllib.request, urllib.error, urllib.parse
from bs4 import BeautifulSoup

# Self
import util
from config import config_helper as config

# =============================================================================

soup_cache = None
cache_time = 0
cache_url = None

def is_post( url ):
	if re.match("^https?://www\.pathofexile\.com/forum/view-thread/\d+/?$", url):
		return True
	
	return False
	
def get_soup_from_url( url ):
	global cache_url
	global cache_time
	global soup_cache
	
	if url != cache_url or time.time() > cache_time + 5:
		try:
			html = util.get_url_data(url)
		except urllib.error.URLError as e:
			logging.error("Failed to retrieve any data\n{}\n{}".format(url, str(e)))
			return None
			
		soup_cache = BeautifulSoup(html, 'html.parser')
		cache_time = time.time()
		cache_url = url
		
	return soup_cache
	
def get_op_body( url ):
	soup = get_soup_from_url( url )
	
	if not soup:
		return None
	
	op_body = soup.select("div.forum-table-container tr:nth-of-type(1) > td.content-container > div.content")
	
	if len(op_body) == 0:
		return " ";
	
	return op_body[0].get_text()
	
def get_op_author( url ):
	soup = get_soup_from_url( url )
	
	if not soup:
		return None
	
	author_link = soup.select("div.forum-table-container tr:nth-of-type(1) div.posted-by a:nth-of-type(2)")
	
	if len(author_link) == 0:
		return None;
	
	
	out_str = "[{:s}](https://pathofexile.com{:s})".format(author_link[0].get_text().encode('utf-8'), author_link[0]['href'])
	
	return out_str