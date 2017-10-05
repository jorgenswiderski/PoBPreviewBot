import re
import util
import config
from bs4 import BeautifulSoup

soup_cache = {}
cache_list = []

def is_post( url ):
	if re.match("^https?://www\.pathofexile\.com/forum/view-thread/\d+/?$", url):
		return True
	
	return False
	
def get_soup_from_url( url ):
	if url not in soup_cache:
		html = util.get_url_data(url)
		soup_cache[url] = BeautifulSoup(html, 'html.parser')
		cache_list.append(url)
		if len(cache_list) > config.max_soup_cache_size:
			# remove the entry at the front of the list
			removed = cache_list.pop(0)
			del soup_cache[removed]
	else:
		# move the url to the back of list again
		cache_list.remove(url)
		cache_list.append(url)
		
	return soup_cache[url]		
	
def get_op_body( url ):
	soup = get_soup_from_url( url )
	
	first_post = soup.select("div.forum-table-container tr:nth-of-type(1) > td.content-container")
	
	return first_post[0].get_text()
	
def get_op_author( url ):
	soup = get_soup_from_url( url )
	
	author_link = soup.select("div.forum-table-container tr:nth-of-type(1) div.posted-by a:nth-of-type(2)")
	
	return "[{:s}](https://pathofexile.com{:s})".format(author_link[0].get_text(), author_link[0]['href'])