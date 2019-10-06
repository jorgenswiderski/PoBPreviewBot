# Python
import json
import logging
import time

# 3rd Party
import praw
from atomicwrites import atomic_write

# Self
import util
from praw_wrapper import praw_object_wrapper_t

class replied_t:
	def __init__(self, file_path):
		self.path = file_path
	
		try:
			with open(file_path, 'r') as f:
				self.dict = util.byteify(json.load(f))
		except IOError:
			self.dict = {}
			pass
			
		logging.debug("Initialized replied to list.")
		
	# Takes an id or an object and returns whether that comment/sub in the list
	def contains(self, obj):
		id = None
		
		if isinstance(obj, (str, unicode)):
			id = obj
		elif isinstance(obj, (praw_object_wrapper_t, praw.models.Comment, praw.models.Submission)):
			id = obj.id
		else:
			raise ValueError("contains passed bad obj: {}".format(type(obj)))
			
		return id in self.dict
		
	def flush(self):
		with atomic_write(self.path, overwrite=True) as f:
			json.dump(self.dict, f, sort_keys=True, indent=4)
		
	def add(self, wo):
		if not isinstance(wo, praw_object_wrapper_t):
			raise ValueError("add passed bad wo: {}".format(type(wo)))
			
		if wo.id in self.dict:
			logging.warning("add was passed {} whose ID is already listed".format(wo))
			
		self.dict[wo.id] = {
			"id": wo.id,
			"type": "comments" if wo.is_comment() else "submissions",
			"time": time.time(),
		}
		
		logging.debug(self.dict[wo.id])
		
		logging.debug("Added {} to replied to list.".format(wo))
		self.flush()
		
	def remove(self, wo):
		if not isinstance(wo, praw_object_wrapper_t):
			raise ValueError("remove passed bad wo: {}".format(type(wo)))
			
		if wo.id not in self.dict:
			raise KeyError()
			
		del self.dict[wo.id]
		
		logging.debug("Removed {} from replied to list.".format(wo))
		self.flush()