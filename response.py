# Python
import re
import os
import traceback
import zlib
import logging

from xml import etree

# 3rd Party
import urllib2
import praw

# Self
import util
from util import obj_type_str
import pastebin
from pob_build import build_t
import config
import comment_maintenance

from pob_build import EligibilityException

# =============================================================================

		
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
			logging.warning("Duplicates detected in pastebin blacklist. Deduplicating...")

			with open("pastebin_blacklist.txt", "w") as f:
				list = []
				
				for k in pastebin_blacklist:
					list.append(k)
					
				f.write( ( '\n'.join(list) ) + '\n' )

			logging.warning("Deduplication complete.")
		
	return pastebin_blacklist
	
def blacklist_pastebin(paste_key):
	if paste_key in pastebin_blacklist:
		return
	
	pastebin_blacklist[paste_key] = True

	with open("pastebin_blacklist.txt", "a") as f:
		f.write(paste_key + "\n")
		
	logging.info("Blacklisted paste key " + paste_key + ".")
	
def paste_key_is_blacklisted(paste_key):
	return paste_key in pastebin_blacklist

def get_response( reddit, reply_object, body, author = None, ignore_blacklist = False ):
	if not (reply_object and ( isinstance( reply_object, praw.models.Comment ) or isinstance( reply_object, praw.models.Submission ) ) ):
		raise Exception("get_response passed invalid reply_object")
	elif not ( body is not None and ( isinstance( body, str ) or isinstance( body, unicode ) ) ):
		raise Exception("get_response passed invalid body")
		
	# If author isn't passed in as a parameter, then default to the author of the object we're replying to
	if not author:
		author = reply_object.author
	
	logging.debug("Processing " + reply_object.id)
		
	if reply_object.author == reddit.user.me():
		logging.debug("Author is self, ignoring")
		return

	if "pastebin.com/" in body:
		responses = []
		bins_responded_to = {}
	
		for match in re.finditer('pastebin\.com/\w+', body):
			bin = "https://" + match.group(0)
			paste_key = pastebin.strip_url_to_key(bin)
			
			if (not paste_key_is_blacklisted(paste_key) or ignore_blacklist) and paste_key not in bins_responded_to:
				try:
					xml = pastebin.get_as_xml(paste_key)
				except (zlib.error, TypeError, etree.ElementTree.ParseError):
					logging.info("Pastebin does not decode to XML data.")
					blacklist_pastebin(paste_key)
					continue
				except urllib2.HTTPError as e:
					logging.error("urllib2 {:s}".format(repr(e)))
					
					if "Service Temporarily Unavailable" not in repr(e):
						blacklist_pastebin(paste_key)
						
					continue
				except urllib2.URLError as e:
					logging.error("Failed to retrieve any data\nURL: {}\n{}".format(raw_url, str(e)))
					util.dump_debug_info(reply_object, exc=e, paste_key=paste_key)
					continue
				
				if xml.tag == "PathOfBuilding":
					if xml.find('Build').find('PlayerStat') is not None:
						try:
							build = build_t(xml, bin, author, reply_object)
							response = build.get_response()
						except EligibilityException:
							blacklist_pastebin(paste_key)
							raise
							continue
						except Exception as e:
							logging.error(repr(e))
							
							# dump xml for debugging later
							util.dump_debug_info(reply_object, exc=e, xml=xml)
							
							blacklist_pastebin(paste_key)
							continue
						
						#util.dump_debug_info(reply_object, xml=xml, dir="xml_dump")
							
						responses.append(response)
						bins_responded_to[paste_key] = True
					else:
						logging.error("XML does not contain player stats.")
						blacklist_pastebin(paste_key)
				else:
					logging.info("Pastebin does not contain Path of Building XML.")
					blacklist_pastebin(paste_key)
		
		if len(responses) > 5:
			raise comment_maintenance.PastebinLimitException("Ignoring {} {} because it has greater than 5 valid pastebins. ({})".format(obj_type_str(reply_object), reply_object.id, len(responses)))
		elif len(responses) > 0:
			comment_body = ""
			if len(responses) > 1:
				for res in responses:
					if comment_body != "":
						comment_body += "\n\n[](#quote_break)  \n"
					comment_body += '>' + res.replace('\n', "\n>")
			else:
				for res in responses:
					comment_body = res + "  \n*****"
				
			comment_body += '\n\n' + config.BOT_FOOTER
			
			return comment_body
			
pastebin_blacklist = get_blacklisted_pastebins()
logging.debug("Pastebin blacklist loaded with {} entries.".format(len(pastebin_blacklist)))