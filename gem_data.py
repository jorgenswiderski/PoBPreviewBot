from enum import Enum
import os
import re
import json

class gem_color(Enum):
	WHITE = 0
	RED = 1
	GREEN = 2
	BLUE = 3

class gem_data_t:
	url_suffix_re = re.compile(".com/(.+?)$")

	def __init__(self, json):
		self.__dict__ = json
		
		# sanitize inputs
		self.color_str = self.color_str.lower()
		self.wiki_url = self.wiki_url.strip()
		
		# set some derived attributes
		self.shortname = self.name.replace(" Support", "")
		self.slug = self.name.replace(" ", "_")
		
		self.color = self.__parse_color__()

	def __parse_color__(self):
		if self.color_str == "red":
			return gem_color.RED
		elif self.color_str == "green":
			return gem_color.GREEN
		elif self.color_str == "blue":
			return gem_color.BLUE
		elif self.color_str == "white":
			return gem_color.WHITE
			
	def get_color_code(self):
		if self.color == gem_color.RED:
			return "#c51e1e"
		elif self.color == gem_color.GREEN:
			return "#08a842"
		elif self.color == gem_color.BLUE:
			return "#4163c9"
			
	def get_url_suffix(self):
		search = self.url_suffix_re.search(self.wiki_url)
		return search.group(1)

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
		
	for data in raw_data:
		gem = gem_data_t(data)
		support_gems[ gem.shortname.lower() ] = gem
			
	return support_gems
	
support_gems = load_gems_from_file("data/support_gems.json")

def get_support_gem_by_name(name):
	if name in support_gems:
		return support_gems[name]
	else:
		raise Exception("{:s} not in support_gems".format(name))