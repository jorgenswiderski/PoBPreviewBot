# Python
import logging

# 3rd Party
import praw

# Self
import util
import official_forum

from response import get_response
from response import PastebinLimitException
from pob_build import EligibilityException

class praw_object_wrapper_t():
	def __init__(self, object):
		self.object = object
		
		# BE CAREFUL
		# Any attributes defined in this object may override/obscure attr
		# defined in the subobject
		
	def __str__(self):
		return "{} {}".format("comment" if isinstance(self.object, praw.models.Comment) else "submission", self.object.id)
		
	def __getattr__(self, name):
		return getattr(self.object, name)
		
	# Override praw parent() to return a wrapped object
	def parent(self):
		return praw_object_wrapper_t(self.object.parent())
		
	def is_comment(self):
		return isinstance(self.object, praw.models.Comment)
		
	def is_submission(self):
		return isinstance(self.object, praw.models.Submission)
		
	def get_body(self):
		o = self.object
	
		if self.is_comment():
			return o.body
		else:
			if o.selftext == '':
				if official_forum.is_post( o.url ):
					body = official_forum.get_op_body( o.url )
					
					if body:
						return body
				
				return o.url
			else:
				return o.selftext 
	
	def get_author(self):
		o = self.object
	
		if self.is_comment():
			return o.author
		else:
			if o.selftext == '' and official_forum.is_post( o.url ):
				author = official_forum.get_op_author( o.url )
				
				if author:
					return author
			
			return o.author
			
	def parse_and_reply(self, reply_queue):
		body = self.get_body()
		author = self.get_author()
	
		if not ( body is not None and ( isinstance( body, str ) or isinstance( body, unicode ) ) ):
			# dump xml for debugging later
			exc = ValueError("parse_generic passed invalid body")
			util.dump_debug_info(self, exc=exc, extra_data={
				'body_type': str(type(body)),
				'body': body,
			})
			blacklist_pastebin(paste_key)
			raise exc
	
		response = None
		
		try:
			# get response text
			response = get_response( self )
		except (EligibilityException, PastebinLimitException) as e:
			print(str(e))
			
		if response is None:
			return False
			
		logging.info("Found matching {}.".format(self))
		
		# post reply
		if config.username == "PoBPreviewBot" or "pathofexile" not in config.subreddits:
			reply_queue.reply(self, response)
		else:
			logging.debug("Reply body:\n" + response)
			
			with open("saved_replies.txt", "a") as f:
				f.write(response + "\n\n\n")
				
		return True