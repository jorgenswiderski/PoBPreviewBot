import re
import util
import config
from bs4 import BeautifulSoup

soup_cache = None
cache_time = 0
cache_url = None

def is_post( url ):
	if re.match("^https?://www\.pathofexile\.com/forum/view-thread/\d+/?$", url):
		return True
	
	return False
	
def get_soup_from_url( url ):
	if url != cache_url or time.time() > cache_time + 5:
		html = util.get_url_data(url)
		soup_cache = BeautifulSoup(html, 'html.parser')
		cache_time = time.time()
		cache_url = url
		
	return soup_cache
	
def get_op_body( url ):
	soup = get_soup_from_url( url )
	
	first_post = soup.select("div.forum-table-container tr:nth-of-type(1) > td.content-container")
	
	return first_post[0].get_text()
	
def get_op_author( url ):
	soup = get_soup_from_url( url )
	
	author_link = soup.select("div.forum-table-container tr:nth-of-type(1) div.posted-by a:nth-of-type(2)")
	
	return "[{:s}](https://pathofexile.com{:s})".format(author_link[0].get_text(), author_link[0]['href'])