# Python
from enum import Enum
import os
import re
import json
import logging

# 3rd Party
import defusedxml.ElementTree as ET

# Self
from name_overrides import skill_overrides
import util

# =============================================================================

class gem_color(Enum):
	WHITE = 0
	RED = 1
	GREEN = 2
	BLUE = 3

class gem_data_t:
	url_suffix_re = re.compile(".com/(.+?)$")
	custom_wiki_urls = {
		"SupportElementalPenetration": "Elemental_Penetration_Support",
		"SupportGreaterSpellEcho": "Greater_Spell_Echo_Support",
	}

	def __init__(self, id, json):
		self.id = id
		self.json = json
		
		if json['base_item'] is not None:
			self.display_name = json['base_item']['display_name']
			#self.id_long = json['base_item']['id']
			
		self.is_support = json['is_support']
		
		self.init_attr(json['static'], 'stat_requirements')
		self.init_attr(json['static'], 'required_level')
		self.init_attr(json, 'secondary_granted_effect')
		self.init_attr(json, 'tags')

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
		self.init_attr(json['active_skill'], 'minion_types')
		
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
			if id in self.custom_wiki_urls:
				self.wiki_url = "https://pathofexile.gamepedia.com/{}".format(self.custom_wiki_urls[id])
			else:
				self.wiki_url = None
		else:
			self.wiki_url = "https://pathofexile.gamepedia.com/{}".format(self.display_name.replace(" ", "_"))
		
		# derived attributes
		self.short_name = self.display_name.replace(" Support", "")
		
def load_gems_from_file(path):
	if not os.path.isfile(path):
		raise Exception("Path to support gem info is invalid. {:s}".format(path))
		
	support_gems = {}
	raw_data = None
	
	with open(path, "r") as f:
		raw_data = util.byteify(json.loads(f.read()))
		
	for id in raw_data:
		data = raw_data[id]
		gem = None
		
		if data['is_support']:
			gem = support_gem_data_t(id, data)
		elif 'active_skill' in data:
			gem = active_gem_data_t(id, data)
		else:
			logging.warning("Could not initialize gem {}".format(id))
			continue
			
		support_gems[ id ] = gem
		logging.debug("Initialized gem {}".format(id))
			
	return support_gems
	
support_gems = load_gems_from_file("data/gems.json")

# list of all support gems' short names
# used for error checking in gem_t.is_supported_by
support_gem_short_name_list = map(lambda g: g.short_name.lower(), filter(lambda g: g.is_support, support_gems.values()))

def get_support_gem_by_name(name):
	if name in support_gems:
		return support_gems[name]
	else:
		raise Exception("{:s} not in support_gems".format(name))
	
class gem_t:
	# Gem name overrides ======================================================
	# Sometimes an item modifier that grants a support gem can be worded,
	# spelled, or punctuated incorrectly. In that case, that incorrect name
	# must be overriden in order to retrieve the proper gem data. For
	# simplicity's sake, just override to the exact id of the gem. See
	# gem_t.get_gem_data for implementation.
	data_overrides = {
		# wrong wording
		'power charge on critical strike': 'SupportPowerChargeOnCrit',
		# Gem has no name in the gem data
		'greater volley': 'UniqueSupportGreaterVolley',
		'elemental penetration': 'SupportElementalPenetration',
		'greater spell echo': 'SupportGreaterSpellEcho',
	}

	def __init__(self, gem_xml, socket_group):
		try:
			self.xml = gem_xml
			
			if 'skillId' not in self.xml.attrib:
				# If the gem has no skillId that means it grants no skills.
				# It is most likely an abyss jewel and can safely be ignored.
				# Return out before this gem object is added to the socket group.
				return
			
			self.build = socket_group.build
			self.socket_group = socket_group
			
			# Append to list now so that self is present in the list when we iterate through gems later.
			self.socket_group.gems.append(self)
			
			self.item = socket_group.item
			
			self.enabled = self.xml.attrib['enabled'].lower() == "true"
			self.enabled_skill_1 = self.xml.attrib['enableGlobal1'].lower() == "true"
			self.enabled_skill_2 = self.xml.attrib['enableGlobal2'].lower() == "true"

			self.id = self.xml.attrib['skillId']
			self.level = int(self.xml.attrib['level'])
			self.quality = int(self.xml.attrib['quality'])
			
			self.__init_gem_data__()
			self.__init_active_skill__()
			self.__set_name__()
		except Exception as e:
			logging.debug("Gem XML:")
			logging.debug(ET.tostring(self.xml))
			logging.debug("gem_t object dict:")
			logging.debug(self.__dict__)
			logging.error("An error occurred when initializing a gem_t. Object information has been dumped to debug log.")
			raise e

	def __str__(self):
		attr_list = []

		attr_list.append("gem='{}'".format(self.id))

		if 'slot' in self.socket_group.xml.attrib:
			attr_list.append("sg_slot='{}'".format(self.socket_group.xml.attrib['slot']))

		if 'label' in self.socket_group.xml.attrib:
			attr_list.append("sg_label='{}'".format(self.socket_group.xml.attrib['label']))

		return "<{}>".format("/".join(attr_list))
		
	def __set_name__(self):
		''' Don't call get_skill_data() here. If we call it here, and
		active skill is NOT a support (ie Shockwave Support) then bad shit happens.

		is_support returns based on data_1, so just always return stuff about data_1 '''
		if self.is_support():
			self.name = self.data.short_name
		else:
			self.name = self.data.display_name
			
		if self.name in skill_overrides:
			self.name = skill_overrides[self.name]
			
	def __init_gem_data__(self):
		self.data = self.get_gem_data(id=self.id)

		if self.data.secondary_granted_effect is not None:
			# gem grants multiple skills
			self.data_2 = self.get_gem_data(id=self.data.secondary_granted_effect)
		else:
			self.data_2 = None
	
	# For gems that grant multiple skills (vaal gems), we need to determine which of these skills is set as the active skill.
	def __init_active_skill__(self):
		if self.socket_group.active_skill > 0 and self.data.secondary_granted_effect is not None:
			#logging.debug("active_skill={}".format(self.socket_group.active_skill))
		
			current_skill = 0
			#logging.debug("current_skill={}".format(current_skill))
			
			for gem in self.socket_group.gems:
				if not gem.enabled:
					continue

				if not gem.data.is_support:
					current_skill += 1

					if current_skill == self.socket_group.active_skill:
						self.active_skill = 1

						if gem.data_2 is not None:
							logging.debug("Build is using primary skill of 2 part gem.")

						return

				if gem.data_2 is not None and not gem.data_2.is_support:
					current_skill += 1
					
					if current_skill == self.socket_group.active_skill:
						self.active_skill = 2
						logging.debug("Build is using secondary skill of 2 part gem.")
						return
					
				#logging.debug("current_skill={}".format(current_skill))

				if gem == self:
					# socket group's active skill must be in a gem whose index is higher than this one, so we're done
					self.active_skill = 1
					return

			logging.debug("{} active skill is disabled, defaulting to 1.".format(self))
			self.active_skill = 1
		else:
			# 1-indexed
			self.active_skill = 1

		if not hasattr(self, 'active_skill'):
			raise RuntimeError("Active skill was not defined.")

	@staticmethod
	def get_gem_data(name=None, id=None):
		# If an override exists for the name, use its overriden ID instead.
		if name is not None and name in gem_t.data_overrides:
			id = gem_t.data_overrides[name]
			name = None
	
		if id is not None:
			if id in support_gems:
				return support_gems[id]
			
			raise GemDataException("Could not find gem data for {}!".format(id))
		elif name is not None:
			name = name.lower()
			
			for id in support_gems:
				data = support_gems[id]
				
				if data.is_support and name == data.short_name.lower():
					return data
			
			raise GemDataException("Could not find gem data for {}!".format(name))
		else:
			exc = ValueError("gem_t.get_gem_data was passed no parameters.")
			util.dump_debug_info(self.build.praw_object, exc=exc, xml=self.build.xml)
			return

	def get_skill_data(self):
		if not hasattr(self, 'active_skill'):
			raise RuntimeError("Trying to access skill data before active_skill is defined") 

		if self.active_skill == 1:
			return self.data
		elif self.active_skill == 2:
			return self.data_2
		else:
			raise ValueError("active_skill has bad value: {}".format(self.active_skill)) 
		
	def get_support_gem_dict(self):
		dict = {}
		
		# Support gems from xml (socketed into the item)
		for gem in self.socket_group.gems:
			if gem.enabled and gem.is_support():
				dict[gem.data.id] = gem.data

		# Merge in all the support gems granted by the item's mods
		if self.item is not None:
			dict.update(self.item.support_mods)
					
		return dict
		
	def is_supported_by(self, support):
		if self.is_support():
			return False

		support = support.lower()

		for id, data in self.get_support_gem_dict().items():
			if data.short_name.lower() == support:
				return True

		# check if such a support even exists in the gem data.
		# if it doesn't, throw an exception. that's indicative of some sort of problem
		if support not in support_gem_short_name_list:
			raise GemDataException("Called is_supported_by with parameter support gem {}, but no such gem exists in gem data.".format(support))
			
		return False
	
	def get_support_gem_str(self):
		str = ""
		
		for id, data in self.get_support_gem_dict().items():
			if data.wiki_url is not None:
				str += "[{:s}]({:s}#support-gem-{:s})".format(data.letter, data.wiki_url, data.get_color_str())
			else:
				str += "[{:s}](#support-gem-{:s})".format(data.letter, data.get_color_str())
				
		return str
	
	def get_num_support_gems(self):
		n = 0
		
		for gem in self.socket_group.gems:
			if gem.enabled and gem.is_support():
				n += 1
		
		return n
			
	def get_num_supports(self):
		return len(self.get_support_gem_dict())
		
	def get_totem_limit(self):
		tl = self.build.get_totem_limit()
		
		if self.name == "Searing Bond":
			tl += 1
			
		'''
		Iron Commander
		NOTE: Stat search is a bit more robust than just checking for the presence
		      of the item, in case the item was renamed or other custom item shenanigans.
		'''
		if self.name == "Siege Ballista Totem":
			totems_per_200 = self.build.get_stat_total('number_of_additional_siege_ballistae_per_200_dexterity')
			tl += totems_per_200 * math.floor( self.build.get_stat("Dex") / 200 )
			
		# Skirmish
		if self.is_attack():
			tl += self.build.get_stat_total('attack_skills_additional_totems_allowed')

		if self.is_supported_by('Multiple Totems'):
			tl += 2

		# base totem override for ballistas
		if "Ballista" in self.name or self.is_supported_by("Ballista Totem"):
			tl += 2

			# FIXME: replace with get_stat_total call once stats on passive skills are support
			if self.build.has_passive_skill("Watchtowers"):
				tl += 1

			if self.build.has_passive_skill("Panopticon"):
				tl += 1

			# "Attack Skills have {0} to maximum number of Summoned Ballista Totems"
			# currently does not include passive skills, only items
			tl += self.build.get_stat_total('attack_skills_additional_ballista_totems_allowed')
			
		return tl
			
	def is_support(self):
		return self.data.is_support
		
	def is_vaal_skill(self):
		if self.is_support():
			return False

		return "vaal" in self.get_skill_data().types
		
	def is_vaal_gem(self):
		return "vaal" in self.data.tags
	
	def is_totem(self):
		if self.is_support():
			return False

		return (self.get_skill_data().is_skill_totem
			or self.is_supported_by("Ballista Totem")
			or self.is_supported_by("Spell Totem"))
		
	def is_mine(self):
		if self.is_support():
			return False

		return "mine" in self.get_skill_data().types or self.is_supported_by("Blastchain Mine") or self.is_supported_by("High-Impact Mine")
	
	def is_trap(self):
		if self.is_support():
			return False

		return "trap" in self.get_skill_data().types or self.is_supported_by("Trap")
		
	def is_attack(self):
		if self.is_support():
			return False

		return "attack" in self.get_skill_data().types
		
	def is_spell(self):
		if self.is_support():
			return False

		return "spell" in self.get_skill_data().types

	def is_attack_minion(self):
		if self.is_support():
			return False

		if self.get_skill_data().minion_types is None:
			return False

		return ("attack" in self.get_skill_data().minion_types
			and "spell" not in self.get_skill_data().minion_types)

	def is_spell_minion(self):
		if self.is_support():
			return False

		if self.get_skill_data().minion_types is None:
			return False

		return ("spell" in self.get_skill_data().minion_types
			and "attack" not in self.get_skill_data().minion_types)
		
	def has_stackable_dot(self):
		if self.name == "Scorching Ray":
			return True
		
		return False
		
	def get_num_mines_laid(self):
		if not self.is_mine():
			raise Exception("get_num_mines_laid() called on non-mine gem!")
			
		mines = 1
			
		if self.is_supported_by("Minefield"):
			mines += 4
		
		# 'Place an additional Mine' stat
		# 'Place {0} additional Mines' stat
		mines += self.build.get_stat_total('number_of_additional_mines_to_place')

		# '{0}% chance when Placing Mines to Place an additional Mine' stat
		mines += self.build.get_stat_total('chance_to_place_an_additional_mine_%') / 100
			
		return mines
	
	def get_num_traps_thrown(self):
		if not self.is_trap():
			raise Exception("get_num_traps_thrown() called on non-trap gem!")
			
		traps = 1
			
		if self.is_supported_by("Multiple Traps"):
			traps += 2
			
		if self.is_supported_by("Cluster Traps"):
			traps += 3
		
		# 'Skills which Throw Traps throw up to 1 additional Trap' stat
		# 'Skills which Throw Traps throw up to {0} additional Traps' stat
		traps += self.build.get_stat_total('number_of_additional_traps_to_throw')

		if self.name == "Fire Trap":
			# 'Fire Trap throws up to 1 additional Trap' stat
			# 'Fire Trap throws up to {0} additional Traps' stat
			traps += self.build.get_stat_total('fire_trap_number_of_additional_traps_to_throw')
			# 'With at least 40 Dexterity in Radius, Fire Trap throws up to 1 additional Trap' stat
			# 'With at least 40 Dexterity in Radius, Fire Trap throws up to {0} additional Traps' stat
			traps += self.build.get_stat_total('local_unique_jewel_fire_trap_number_of_additional_traps_to_throw_with_40_dex_in_radius')
			
		return traps

	def has_skill(self, name, enabled=False):
		if self.data.display_name.lower() == name.lower():
			if enabled:
				return self.enabled and self.enabled_skill_1
			else:
				return True
		elif self.data_2 is not None and self.data_2.display_name.lower() == name.lower():
			if enabled:
				return self.enabled and self.enabled_skill_2
			else:
				return True
		
		return False