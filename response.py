# Python
import re
import os
import traceback
import logging

# 3rd Party
import urllib2
import praw

# Self
import util
from importers import Pastebin
from importers import PoBParty
from config import config_helper as config
import comment_maintenance
from praw_wrapper import praw_object_wrapper_t
from pob_build import build_t

from _exceptions import EligibilityException
from _exceptions import ImporterLimitException

# =============================================================================

def find_importers(body):
	for match in re.finditer('pastebin\.com/\w+', body):
		bin = "https://" + match.group(0)
		yield Pastebin(url=bin)

	for match in re.finditer('pob\.party/share/\w+', body):
		url = "https://" + match.group(0)
		yield PoBParty(url=url)

# =============================================================================

def get_response( wrapped_object, ignore_blacklist=False ):
	if not (wrapped_object is not None and isinstance( wrapped_object, praw_object_wrapper_t )):
		raise ValueError("get_response was passed an invalid wrapped_object: {}".type(wrapped_object))
		
	author = wrapped_object.get_author()
	body = wrapped_object.get_body()
	
	logging.debug("Processing {}".format(wrapped_object))

	if ("pastebin.com/" in body or "pob.party/share/" in body):
		responses = []
		importers_responded_to = {}
	
		for importer in find_importers(body):
			if (not importer.is_blacklisted() or ignore_blacklist):
				if importer.key not in importers_responded_to:
					if importer.is_pob_xml():
						try:
							build = build_t(importer, author, wrapped_object)
							response = build.get_response()
						except EligibilityException:
							importer.blacklist()
							raise
							continue
						except Exception as e:
							logging.error(repr(e))
							
							# dump xml for debugging later
							util.dump_debug_info(wrapped_object, exc=e, xml=importer.xml())
							
							importer.blacklist()
							continue
						
						if config.xml_dump:
							util.dump_debug_info(wrapped_object, xml=importer.xml(), dir="xml_dump")
							
						responses.append(response)
						importers_responded_to[importer.key] = True
					else:
						logging.debug("Skipped {} as it is not valid PoB XML.".format(importer))
				else:
					logging.debug("Skipped {} as it is already included in this response.".format(importer))
			else:
				logging.debug("Skipped {} as it is blacklisted.".format(importer))
		
		if len(responses) > 5:
			raise ImporterLimitException("Ignoring {} because it has more than 5 valid importers. ({})".format(wrapped_object, len(responses)))
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
	else:
		logging.debug("{} includes no pastebins.".format(wrapped_object))
			
def reply_to_summon(bot, comment, ignore_blacklist=False):
	if not isinstance(comment, praw_object_wrapper_t):
		raise ValueError("reply_to_summon was passed an invalid comment: {}".format(type(comment)))

	errs = []
	parent = comment.parent()

	logging.debug("Comment {} summons {}, parent is comment {}.".format(comment.id, config.username, parent.id))
	
	if parent.author == bot.reddit.user.me():
		return
		
	p_response = None
	
	try:
		if parent.is_comment():
			p_response = get_response( comment )
	except (EligibilityException, ImporterLimitException) as e:
		errs.append("* {}".format(str(e)))
	
	response = None
		
	if p_response is not None and not bot.replied_to.contains(parent) and not bot.reply_queue.contains_id(parent.id):
		logging.debug("Comment {} has valid response, queued replies to both comments.".format(parent.id))

		if config.username == "PoBPreviewBot" or "pathofexile" not in config.subreddits:
			bot.reply_queue.reply(parent, p_response)

		response = "Seems like I missed comment {}! I've replied to it now, sorry about that.".format(parent.id)
	elif len(errs) > 0:
		logging.debug("Exception occurred when getting response for comment {}, queueing reply with summary.".format(parent.id))
		response = "The {} {} was not responded to for the following reason{}:\n\n{}".format(parent, parent.id, "s" if len(errs) > 1 else "", "  \n".join(errs))
	else:
		logging.debug("Comment {} has no response or exceptions, queueing reply with intro.".format(parent.id))
		response = config.BOT_INTRO
	
	if response is None:
		return
	
	if config.username == "PoBPreviewBot" or "pathofexile" not in config.subreddits:
		bot.reply_queue.reply(comment, response, log = False)
		
		
		
		