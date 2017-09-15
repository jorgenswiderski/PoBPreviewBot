from enum import Enum
import os
import re

class gem_color(Enum):
	WHITE = 0
	RED = 1
	GREEN = 2
	BLUE = 3

class gem_data_t:
	def __init__(self, tsv_info):
		info = tsv_info.split("\t")
		self.name = info[0]
		self.shortname = self.name.replace(" Support", "")
		self.color_str = info[1].lower()
		self.shortcode = info[2]
		self.wiki_url = info[3].strip()
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
		

def load_gems_from_file(path):
	if not os.path.isfile(path):
		raise Exception("Path to support gem info is invalid. {:s}".format(path))
		
	support_gems = {}
	
	with open(path, "r") as f:
		gems = f.read()
		gems = gems.split("\n")
		gems = filter(None, gems)
		
		for gem in gems:
			gem = gem_data_t( gem )
			support_gems[ gem.shortname ] = gem
			
	return support_gems
	
support_gems = load_gems_from_file("data/support_gems.tsv")

def get_support_gem_by_name(name):
	if name in support_gems:
		return support_gems[name]
	else:
		raise Exception("{:s} not in support_gems".format(name))