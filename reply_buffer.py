# Python
from collections import deque
import time
import math
import logging
import json

# 3rd Party
import praw

from praw.exceptions import APIException
from prawcore.exceptions import ServerError

# Self
import util
from comment_maintenance import maintain_list_t
from praw_wrapper import praw_object_wrapper_t

# =============================================================================

class reply_handler_t:
	_throttled_until = 0

	def __init__(self, bot):
		self.bot = bot
		self.maintain_list = bot.maintain_list
		self.replied_to = bot.replied_to
		self.queue_dict = {}
		self.queue = deque()
		
	def reply(self, object, message_body, log = True):
		if not isinstance(object, praw_object_wrapper_t):
			raise ValueError("reply was passed an invalid object: {}".format(type(object)))
		
		rep = reply_t( self, object, message_body, log )
		
		if self.throttled():
			self.append( rep )
			logging.info("Added response to {} to reply queue.".format(rep.object))
		else:
			rep.attempt_post()
			
			if not rep.resolved:
				self.append( rep )
				logging.info("Reply failed. Added response to {} to reply queue.".format(rep.object))
				
	def throttled(self):
		return reply_handler_t._throttled_until > time.time()
		
	def throttled_for(self):
		return math.max(0, reply_handler_t._throttled_until - time.time() )
	
	def throttled_until(self):
		return reply_handler_t._throttled_until
			
	def append(self, rep):
		self.queue.append( rep )
		
		if rep.object.id in self.queue_dict:
			self.queue_dict[ rep.object.id ] += 1
		else:
			self.queue_dict[ rep.object.id ] = 1
	
	def contains_id(self, id):
		return id in self.queue_dict
		
	def __len__(self):
		return len(self.queue)
		
	def is_active(self):
		return len(self.queue) > 0 and not self.throttled()
				
	def process(self):
		while self.is_active():
			logging.debug("Processing reply queue entry (of {})".format( len(self) ))
			self.queue[0].attempt_post()
			
			if self.queue[0].resolved:
				rep = self.queue.popleft()
				self.queue_dict[ rep.object.id ] -= 1
				
				if self.queue_dict[ rep.object.id ] <= 0:
					del self.queue_dict[ rep.object.id ];
		
class reply_t:
	def __init__(self, handler, object, message_body, log):
		if not isinstance(object, praw_object_wrapper_t):
			raise ValueError("init was passed an invalid object: {}".format(type(object)))
			
		self.handler = handler
		self.object = object
		self.message_body = message_body
		self.req_maintenance = log
		self.resolved = False
		
	def attempt_post( self ):
		if self.resolved:
			return
	
		try:
			comment = self.object.reply( self.message_body )
			
			logging.info("Replied to {} with {}.".format(self.object, comment))
	
			self.handler.replied_to.add(self.object)
			
			if self.req_maintenance:
				self.handler.maintain_list.add( comment )
				
			self.resolved = True
		except APIException as e:
			if "DELETED_COMMENT" in str(e):
				self.resolved = True
				logging.warning("Parent {} has been deleted before it could be responded to. Removing response from reply queue.".format(self.object))
			elif "TOO_OLD" in str(e):
				self.resolved = True
				logging.warning("Ignoring {} as it is too old to be responded to.".format(self.object))
			else:
				logging.warning("Failed to reply {}, buffering reply for later.".format(repr(e)))
				reply_handler_t._throttled_until = time.time() + 60
				
				self.resolved = False
		except ServerError as e:
			logging.error("{} occurred while attempting to post response to {}. Stack trace dumped.".format(e, self.object))
			logging.debug(self.object.permalink())
			logging.debug(e, exc_info=True)
			self.resolved = False