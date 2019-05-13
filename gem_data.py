# Python
from enum import Enum
import os
import re
import json
import logging

# Self
import util

# =============================================================================

class gem_color(Enum):
	WHITE = 0
	RED = 1
	GREEN = 2
	BLUE = 3

class gem_data_t:
	url_suffix_re = re.compile(".com/(.+?)$")

	def __init__(self, id, json):
		self.id = id
		self.json = json
		
		if json['base_item'] is not None:
			self.display_name = json['base_item']['display_name']
			#self.id_long = json['base_item']['id']
			
		self.is_support = json['is_support']
		self.tags = json['tags']
		
		self.init_attr(json['static'], 'stat_requirements')
		self.init_attr(json['static'], 'required_level')

	def get_color(self):
		if self.tags is not None:
			if "strength" in self.tags:
				return gem_color.RED
			elif "dexterity" in self.tags:
				return gem_color.GREEN
			elif "intelligence" in self.tags:
				return gem_color.BLUE
			
		return gem_color.WHITE
			
	def get_color_code(self):
		color = self.get_color()
		
		if color == gem_color.RED:
			return "#c51e1e"
		elif color == gem_color.GREEN:
			return "#08a842"
		elif color == gem_color.BLUE:
			return "#4163c9"
			
	def get_color_str(self):
		color = self.get_color()
		
		if color == gem_color.RED:
			return "red"
		elif color == gem_color.GREEN:
			return "green"
		elif color == gem_color.BLUE:
			return "blue"
		elif color == gem_color.WHITE:
			return "white"
			
	def get_url_suffix(self):
		search = self.url_suffix_re.search(self.wiki_url)
		return search.group(1)
	
	# Initialize an attribute, setting its value to None if the key does not
	# exist in the JSON.
	def init_attr(self, dict, key):
		val = None
		
		if key in dict:
			val = dict[key]
		
		setattr(self, key, val)
		
class active_gem_data_t(gem_data_t):
	def __init__(self, id, json):
		gem_data_t.__init__(self, id, json)
		
		self.description = json['active_skill']['description']
		self.is_manually_casted = json['active_skill']['is_manually_casted']
		self.is_skill_totem = json['active_skill']['is_skill_totem']
		self.types = json['active_skill']['types']
		self.weapon_restrictions = json['active_skill']['weapon_restrictions']
		self.cast_time = json['cast_time']
			
		self.init_attr(json['static'], 'cooldown')
		self.init_attr(json['static'], 'stored_uses')
		
		if json['base_item'] is None:
			self.display_name = json['active_skill']['display_name']
			
		# derived attributes
		self.wiki_url = "https://pathofexile.gamepedia.com/{}".format(self.display_name.replace(" ", "_"))
		
class support_gem_data_t(gem_data_t):
	def __init__(self, id, json):
		gem_data_t.__init__(self, id, json)
		
		self.letter = json['support_gem']['letter']
		self.supports_gems_only = json['support_gem']['supports_gems_only']
			
		self.init_attr(json['static'], 'mana_multiplier')
		
		if json['base_item'] is None:
			self.display_name = id
			self.wiki_url = None
		else:
			self.wiki_url = "https://pathofexile.gamepedia.com/{}".format(self.display_name.replace(" ", "_"))
		
		# derived attributes
		self.short_name = self.display_name.replace(" Support", "")

# Used to convert json.loads() output's keys and values from unicode to strings
def byteify(input):
    if isinstance(input, dict):
        return {byteify(key): byteify(value)
                for key, value in input.iteritems()}
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input
		
def load_gems_from_file(path):
	if not os.path.isfile(path):
		raise Exception("Path to support gem info is invalid. {:s}".format(path))
		
	support_gems = {}
	raw_data = None
	
	with open(path, "r") as f:
		raw_data = byteify(json.loads(f.read()))
		
	for id in raw_data:
		data = raw_data[id]
		gem = None
		
		if data['is_support']:
			gem = support_gem_data_t(id, data)
		elif 'active_skill' in data:
			gem = active_gem_data_t(id, data)
		else:
			util.tprint("Could not initialize gem {}".format(id))
			continue
			
		support_gems[ id ] = gem
		logging.debug("Initialized gem {}".format(id))
			
	return support_gems
	
support_gems = load_gems_from_file("data/gems.json")

def get_support_gem_by_name(name):
	if name in support_gems:
		return support_gems[name]
	else:
		raise Exception("{:s} not in support_gems".format(name))