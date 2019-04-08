import praw
import re
import os
import urllib2
import traceback
import zlib

import util
import pastebin
from pob_build import build_t
import config

from pob_build import EligibilityException
import comment_maintenance 
from util import obj_type_str
		
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
			print "Deduplicating pastebin blacklist."
			with open("pastebin_blacklist.txt", "w") as f:
				list = []
				
				for k in pastebin_blacklist:
					list.append(k)
					
				f.write( ( '\n'.join(list) ) + '\n' )
		
	return pastebin_blacklist
	
def blacklist_pastebin(paste_key):
	if paste_key in pastebin_blacklist:
		return
	
	pastebin_blacklist[paste_key] = True

	with open("pastebin_blacklist.txt", "a") as f:
		f.write(paste_key + "\n")
		
	print "Blacklisted paste key " + paste_key + "."
	
def paste_key_is_blacklisted(paste_key):
	return paste_key in pastebin_blacklist

def get_response( reddit, reply_object, body, author = None, ignore_blacklist = False ):
	if not (reply_object and ( isinstance( reply_object, praw.models.Comment ) or isinstance( reply_object, praw.models.Submission ) ) ):
		raise Exception("get_response passed invalid reply_object")
	elif not ( body and ( isinstance( body, str ) or isinstance( body, unicode ) ) ):
		raise Exception("get_response passed invalid body")
		
	# If author isn't passed in as a parameter, then default to the author of the object we're replying to
	if not author:
		author = reply_object.author
	
	#print "Processing " + reply_object.id
		
	if reply_object.author == reddit.user.me():
		#print "Author is self, ignoring"
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
				except (zlib.error, TypeError, xml.etree.ElementTree.ParseError):
					print "Pastebin does not decode to XML data."
					blacklist_pastebin(paste_key)
					continue
				except urllib2.HTTPError as e:
					print "urllib2 {:s}".format(repr(e))
					
					if "Service Temporarily Unavailable" not in repr(e):
						blacklist_pastebin(paste_key)
						
					continue
				
				if xml.tag == "PathOfBuilding":
					if xml.find('Build').find('PlayerStat') is not None:
						try:
							build = build_t(xml, bin, author)
							response = build.get_response()
						except EligibilityException:
							blacklist_pastebin(paste_key)
							raise
							continue
						except Exception as e:
							print repr(e)
						
							# dump xml for debugging later
							try:
								c = util.get_url_data("http://pastebin.com/raw/" + paste_key)
							except urllib2.HTTPError as e2:
								print "An exception occurred when parsing a comment, but debug data was unable to be dumped."
							c = c.replace("-", "+").replace("_", "/")
							
							if not os.path.exists("error/" + reply_object.id):
								os.makedirs("error/" + reply_object.id)
							
							with open("error/" + reply_object.id + "/pastebin.xml", "w") as f:
								f.write( pastebin.decode_base64_and_inflate(c) )
							with open("error/" + reply_object.id + "/info.txt", "w") as f:
								comment_id = False
								if isinstance(reply_object, praw.models.Comment):
									comment_id = reply_object.permalink
								else:
									comment_id = reply_object.permalink
									
								f.write( "pastebin_url\t{:s}\ncomment_id\t{:s}\ncomment_url\t{:s}\nerror_text\t{:s}".format( bin, reply_object.id,
								 comment_id, repr(e) ))
							with open("error/" + reply_object.id + "/traceback.txt", "w") as f:
								traceback.print_exc( file = f )
							
							print "Dumped info to error/{:s}/".format( reply_object.id )
							blacklist_pastebin(paste_key)
							continue
						
						'''
						with open("xml_dump/{}.xml".format(paste_key), "w") as f:
							try:
								c = util.get_url_data("http://pastebin.com/raw/" + paste_key)
								c = c.replace("-", "+").replace("_", "/")
								f.write( pastebin.decode_base64_and_inflate(c) )
								print "Dumped {} xml to xml_dump/{}.xml".format(reply_object.id, paste_key)
							except:
								pass
						'''
							
						responses.append(response)
						bins_responded_to[paste_key] = True
					else:
						print "XML does not contain player stats."
						blacklist_pastebin(paste_key)
				else:
					print "Pastebin does not contain Path of Building XML."
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
#print pastebin_blacklist