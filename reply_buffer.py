# Python
from collections import deque
import time
import math
import logging

# 3rd Party
import praw

from praw.exceptions import APIException

# Self
import util
from comment_maintenance import maintain_list_t

# =============================================================================

class reply_handler_t:
	_throttled_until = 0

	def __init__(self, maintain_list):
		self.maintain_list = maintain_list
		self.queue_dict = {}
		self.queue = deque()
		
	def reply(self, object, message_body, log = True):
		rep = reply_t( self, object, message_body, log )
		
		if self.throttled():
			self.append( rep )
			logging.info("Added response to {} to reply queue.".format(util.praw_obj_str(rep.object)))
		else:
			rep.attempt_post()
			
			if not rep.resolved:
				self.append( rep )
				logging.info("Reply failed. Added response to {} to reply queue.".format(util.praw_obj_str(rep.object)))
				
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
				
	def process(self):
		while len(self.queue) > 0 and not self.throttled():
			logging.debug("Processing reply queue entry (of {})".format( len(self) ))
			self.queue[0].attempt_post()
			
			if self.queue[0].resolved:
				rep = self.queue.popleft()
				self.queue_dict[ rep.object.id ] -= 1
				
				if self.queue_dict[ rep.object.id ] <= 0:
					del self.queue_dict[ rep.object.id ];
		
class reply_t:
	def __init__(self, handler, object, message_body, log):
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
			
			logging.info("Replied to {} with {}.".format(util.praw_obj_str(self.object), util.praw_obj_str(comment)))
	
			if isinstance(self.object, praw.models.Comment):
				self.handler.maintain_list.comments_replied_to.append(self.object.id)
			else:
				self.handler.maintain_list.submissions_replied_to.append(self.object.id)

			with open("{:s}s_replied_to.txt".format(util.obj_type_str(self.object)), "a") as f:
				f.write(self.object.id + "\n")
			
			if self.req_maintenance:
				self.handler.maintain_list.add( comment )
				
			self.resolved = True
		except APIException as e:
			if "DELETED_COMMENT" in str(e):
				self.resolved = True
				logging.warning("Parent {} has been deleted before it could be responded to. Removing response from reply queue.".format(util.praw_obj_str(self.object)))
			elif "TOO_OLD" in str(e):
				self.resolved = True
				logging.warning("Ignoring {} as it is too old to be responded to.".format(util.praw_obj_str(self.object)))
			else:
				logging.warning("Failed to reply {}, buffering reply for later.".format(repr(e)))
				reply_handler_t._throttled_until = time.time() + 60
				
				self.resolved = False