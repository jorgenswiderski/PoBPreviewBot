# Python
import base64
import re
import logging

# 3rd Party
import praw.models

# Self
import util
import pastebin
import logger
import pob_party
import passive_skill_tree as passives
from name_overrides import skill_overrides
from name_overrides import build_defining_uniques
from gem_data import support_gems as support_gem_data

from _exceptions import UnsupportedException
from _exceptions import GemDataException
from _exceptions import EligibilityException
from _exceptions import PoBPartyException

# =============================================================================

ERR_CHECK_ACTIVE_SKILL = 'Please make sure the correct skill is selected in the left panel when you export!'

stats_to_parse = [
	{
		'elementType': 'PlayerStat',
		'key': 'player',
		'stats': [
			"Life",
			"ManaUnreserved",
			"EnergyShield",
			"MeleeEvadeChance",
			"PhysicalDamageReduction",
			"BlockChance",
			"SpellBlockChance",
			"AttackDodgeChance",
			"SpellDodgeChance",
			"FireResist",
			"ColdResist",
			"LightningResist",
			"TotalDPS",
			"TotalDot",
			"AverageDamage",
			"Speed",
			"CritChance",
			"CritMultiplier",
			"ActiveMinionLimit",
			"LifeUnreservedPercent",
			"DecayDPS",
			"WithPoisonDPS",
			"LifeUnreserved",
			"BleedDPS",
			"IgniteDPS",
			"MineLayingTime",
			"TrapThrowingTime",
			"WithPoisonAverageDamage",
			"Str",
			"Dex",
			"Int",
			"TrapCooldown",
			"Spec:LifeInc",
			"Spec:ManaInc",
			"Spec:EnergyShieldInc",
			"Cooldown",
		],
	},
	{
		'elementType': 'MinionStat',
		'key': 'minion',
		'stats': [
			"TotalDPS",
			"WithPoisonDPS",
			'Speed',
		],
	},
]
	
class socket_group_t:
	def __init__(self, skill_xml, build):
		self.xml = skill_xml
		self.build = build
		
		self.__parse_active_skill__()
		self.__parse_parent_item__()
		self.__create_gems__()
		
	def __parse_active_skill__(self):
		# index of the active skill in this socket group. 1-indexed. a value of 0 indicates the group has no active skill
		if self.xml.attrib['mainActiveSkill'] == 'nil':
			self.active_skill = 0
		else:
			self.active_skill = int(self.xml.attrib['mainActiveSkill']);
	
	def __create_gems__(self):
		self.gems = []
		
		for gem_xml in self.xml.findall('Gem'):
			gem_t(gem_xml, self)
			
	def __parse_parent_item__(self):
		if 'slot' in self.xml.attrib:
			slot = self.xml.attrib['slot']
			
			if slot in self.build.equipped_items:
				self.item = self.build.equipped_items[slot]
				return
		
		self.item = None
		
	def get_gem_of_nth_active_skill(self, n):
		current_skill = 0
		
		for gem in self.gems:
			if not gem.is_support() and gem.enabled:
				if gem.is_vaal_gem():
					current_skill += 2
				else:
					current_skill += 1
			
				if current_skill >= n:
					return gem
				
					
		if current_skill > 1:
			raise Exception('mainActiveSkill exceeds total number of active skill gems in socket group.')
		else:
			raise EligibilityException('Active skill group contains no active skill gems. {}'.format(ERR_CHECK_ACTIVE_SKILL))
			
	def getActiveGem(self):
		if self.active_skill == 0:
			return False
	
		return self.get_gem_of_nth_active_skill(self.active_skill)
	
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
	}

	def __init__(self, gem_xml, socket_group):
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
		self.id = self.xml.attrib['skillId']
		self.level = int(self.xml.attrib['level'])
		self.quality = int(self.xml.attrib['quality'])
		
		self.__init_gem_data__()
		self.__init_active_skill__()
		self.__set_name__()
		
	def __set_name__(self):
		if self.is_support():
			self.name = self.get_skill_data().short_name
		else:
			self.name = self.get_skill_data().display_name
			
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

				if gem.data_2 is not None and not gem.data_2.is_support:
					current_skill += 1
					
				#logging.debug("current_skill={}".format(current_skill))
				
				if current_skill == self.socket_group.active_skill:
					self.active_skill = 2
					logging.debug("Build is using secondary skill of vaal gem.")
					return
				elif gem == self:
					# socket group's active skill must be in a gem whose index is higher than this one, so we're done
					self.active_skill = 1
					return
		else:
			# 1-indexed
			self.active_skill = 1

	@staticmethod
	def get_gem_data(name=None, id=None):
		# If an override exists for the name, use its overriden ID instead.
		if name is not None and name in gem_t.data_overrides:
			id = gem_t.data_overrides[name]
			name = None
	
		if id is not None:
			if id in support_gem_data:
				return support_gem_data[id]
			
			raise GemDataException("Could not find gem data for {}!".format(id))
		elif name is not None:
			name = name.lower()
			
			for id in support_gem_data:
				data = support_gem_data[id]
				
				if data.is_support and name == data.short_name.lower():
					return data
			
			raise GemDataException("Could not find gem data for {}!".format(name))
		else:
			exc = ValueError("gem_t.get_gem_data was passed no parameters.")
			util.dump_debug_info(self.build.praw_object, exc=exc, xml=self.build.xml)
			return

	def get_skill_data(self):
		if self.active_skill == 1:
			return self.data
		elif self.active_skill == 2:
			return self.data_2
		else:
			raise RuntimeError("Trying to access skill data before active_skill is defined") 
		
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
			
		if self.name == "Siege Ballista Totem" and self.build.has_item_equipped("Iron Commander"):
			tl += math.floor( self.build.get_stat("Dex") / 200 )
			
		if self.build.has_item_equipped("Skirmish") and self.is_attack() and self.is_totem():
			tl += 1
			
		return tl
			
	def is_support(self):
		return self.data.is_support
		
	def is_vaal_skill(self):
		return "vaal" in self.get_skill_data().tags
		
	def is_vaal_gem(self):
		return "vaal" in self.data.tags
	
	def is_totem(self):
		if self.is_support():
			raise RuntimeError("Cannot call is_totem on a support gem.")

		return (self.get_skill_data().is_skill_totem
			or self.is_supported_by("Ranged Attack Totem")
			or self.is_supported_by("Spell Totem"))
		
	def is_mine(self):
		return "mine" in self.get_skill_data().tags or self.is_supported_by("Remote Mine")
	
	def is_trap(self):
		return "trap" in self.get_skill_data().tags or self.is_supported_by("Trap")
		
	def is_attack(self):
		return "attack" in self.get_skill_data().tags
		
	def is_spell(self):
		return "spell" in self.get_skill_data().tags
		
	def has_stackable_dot(self):
		if self.name == "Scorching Ray":
			return True
		
		return False
		
	def get_num_mines_laid(self):
		if not self.is_mine():
			raise Exception("get_num_mines_laid() called on non-mine gem!")
			
		mines = 1
			
		if self.is_supported_by("Minefield"):
			mines += 2
		
		# Check for item mods
		mines += len(self.build.item_mod_search("Place an additional Mine"))
		
		matches = self.build.item_mod_search("Place (\d+) additional Mines")
		
		for match_obj in matches:
			mines += int(match_obj.group(1))
			
		return mines
	
	def get_num_traps_thrown(self):
		if not self.is_trap():
			raise Exception("get_num_traps_thrown() called on non-trap gem!")
			
		traps = 1
			
		if self.is_supported_by("Multiple Traps"):
			traps += 2
			
		if self.is_supported_by("Cluster Traps"):
			traps += 3
		
		# Check for item mods
		traps += len(self.build.item_mod_search("Skills which Throw Traps throw an additional Trap"))
		
		matches = self.build.item_mod_search("Skills which Throw Traps throw (\d+) additional Traps")
		
		for match_obj in matches:
			traps += int(match_obj.group(1))
			
		return traps
		
class item_t:
	re_variant = re.compile("^Variant: .+")
	re_reqs = re.compile("^Requires Level \d+")
	re_implicits = re.compile("^Implicits: \d+")
	re_support_mod = re.compile("socketed gems are supported by level \d+ (.+)")
	re_variant_tag = re.compile("{variant:([\d,]+)}")

	def __init__(self, build, item_xml):
		self.build = build
		self.xml = item_xml
		self.id = int(self.xml.attrib['id'])
		
		# set by build_t.__parse_items__()
		self.slot = None
		
		self.__parse_xml__()
		
	def __parse_xml__(self):
		rows = self.xml.text.split('\n')
		
		#logging.debug(repr(rows))
		
		reg = re.compile("Rarity: ([A-Z])+")
		s = reg.search(rows[1])
		
		if not s:
			raise Exception('Failure to parse rarity of Item id={:.0f}'.format(self.id))
			
		self.rarity = s.group(1)
		
		self.name = rows[2].strip()
		self.base = rows[3].strip()
		
		self.__parse_mods__(rows)
		self.__parse_for_support_gems__()
		
	def __parse_mods__(self, rows):
		self.mods = []
		for i in range(4, len(rows)):
			if self.re_variant.search(rows[i]):
				continue
			if self.re_reqs.search(rows[i]):
				continue
			if self.re_implicits.search(rows[i]):
				continue
				
			if self.is_mod_active(rows[i]):
				self.mods.append(rows[i])
		
	def __parse_for_support_gems__(self):
		self.support_mods = {}
	
		for r in self.mods:
			# Match in lower case just in case the mod has improper capitalization
			s = self.re_support_mod.search(r.lower())
			
			if s:
				name = s.group(1).strip()
				data = gem_t.get_gem_data(name=name)
				
				if data:
					self.support_mods[data.id] = data
				else:
					logging.warning("Support gem '{}' was not found in gem data and was ommitted in gem str!".format(name));
					util.dump_debug_info(self.build.praw_object, xml=self.build.xml)
	
	def grants_support_gem(self, support):
		return support.lower() in self.support_mods
		
	def is_mod_active(self, mod):
		# If there's a variant tag, skip any mods who require a variant different than the one the item is using.
		var = self.re_variant_tag.search(mod)
		
		if var:
			if 'variant' not in self.xml.attrib:
				raise Exception("Item {} does not have attrib variant".format(self.id))
				
			req_variants = [int(v) for v in var.group(1).split(",")]
			
			if int(self.xml.attrib['variant']) not in req_variants:
				#print("Ignoring row (v={}): {}", int(self.xml.attrib['variant']), rows[i])
				return False
				
			#print("Row is valid (v={}): {}", int(self.xml.attrib['variant']), rows[i])
			
		return True

class build_t:
	config_bools = {
		"conditionFullLife": "Full Life",
		"conditionKilledRecently": "Killed Recently",
		"conditionEnemyMoving": "Enemy Moving",
		"conditionEnemyShocked": "Shock",
		#"conditionEnemyBlinded": "Blind",
		"buffUnholyMight": "Unholy Might",
		#"buffPhasing": "Phasing",
		"conditionEnemyCoveredInAsh": "Covered in Ash",
		"buffOnslaught": "Onslaught",
		"conditionEnemyMaimed": "Maim",
		"conditionEnemyIntimidated": "Intimidate",
		"conditionEnemyBleeding": "Bleed",
		#"buffFortify": "Fortify",
		"conditionOnConsecratedGround": "Cons. Ground",
	}
	
	config_numbers = {
		"enemyFireResist": "{:+n}% Fire Res",
		"enemyColdResist": "{:+n}% Cold Res",
		"enemyLightningResist": "{:+n}% Light Res",
		"enemyChaosResist": "{:+n}% Chaos Res",
		"enemyPhysicalReduction": "{:+n}% Phys Reduction",
		"multiplierPoisonOnEnemy": "Poison \({:n}\)",
		#"heraldOfAgonyVirulenceStack": "Virulence \({:n}\)",
		"aspectOfTheSpiderWebStacks": "Spider's Web \({:n}\)",
	}
	
	config_strs = {
		"waveOfConvictionExposureType": "{} Exposure",
	}
	
	# Dict of Wither Stacks by its corresponding skillPart
	wither_stacks = {
		"1": 1,
		"2": 5, 
		"3": 10,
		"4": 15,
	}
	
	def __init__(self, pastebin, author, praw_object):
		self.xml = pastebin.xml()
		self.xml_build = self.xml.find('Build')
		self.xml_config = self.xml.find('Config')
		self.pastebin = pastebin
		self.praw_object = praw_object
		
		self.__parse_items__()
		self.__parse_author__(author)
		self.__parse_stats__()
		self.__parse_passive_skills__()
		self.__parse_character_info__()
		
		self.__check_build_eligibility__()
		
	def __parse_author__(self, author):
		if isinstance(author, praw.models.reddit.redditor.Redditor):
			self.author = "/u/{:s}".format(author.name)
		elif isinstance(author, (str, unicode)):
			self.author = author
		else:
			# FIXME: This exception should NOT cause the pastbin to be blacklisted.
			raise Exception('Build has invalid author')
		
	def __parse_character_info__(self):
		self.class_name = self.xml_build.attrib['className']
		
		if self.xml_build.attrib['ascendClassName'] != "None":
			self.ascendancy_name = self.xml_build.attrib['ascendClassName']
			
		self.level = int(self.xml_build.attrib['level'])
		
		self.__parse_main_socket_group__()
		self.__parse_main_gem__()
		
	def __parse_main_socket_group__(self):
		main_socket_group = int(self.xml_build.attrib['mainSocketGroup'])
		skills = self.xml.find('Skills')
		if len(skills) == 0:
			raise EligibilityException('Build has no active skills.')
		self.main_socket_group = socket_group_t(skills[main_socket_group-1], self)
		
		# check to make sure main socket group is not in an inactive weapon set
		if 'slot' in self.main_socket_group.xml.attrib and "Weapon" in self.main_socket_group.xml.attrib['slot']:
			useSecondWeaponSet = self.xml.find('Items').attrib['useSecondWeaponSet'].lower() == "true"
			slot = self.main_socket_group.xml.attrib['slot']
			
			if ( not useSecondWeaponSet and "Swap" in slot ) or ( useSecondWeaponSet and "Swap" not in slot ):
				raise EligibilityException('The active skill gem is socketed in an inactive weapon (ie weapon swap).')
		
	def __parse_main_gem__(self):
		if self.main_socket_group is None:
			self.__parse_main_socket_group__()
		
		self.main_gem = self.main_socket_group.getActiveGem()
		
		if not self.main_gem:
			raise EligibilityException('Active skill group contains no active skill gems. {}'.format(ERR_CHECK_ACTIVE_SKILL))
		
	def __parse_stats__(self):
		self.stats = {}
	
		for entry in stats_to_parse:
			key = entry['key']
			elementType = entry['elementType']
			self.stats[key] = {}
			
			for stat in self.xml_build.findall(elementType):
				if stat.attrib['stat'] in entry['stats']:
					self.stats[key][stat.attrib['stat']] = float(stat.attrib['value'])
					
			for stat in entry['stats']:
				if stat not in self.stats[key]:
					self.stats[key][stat] = 0
					
	def __parse_passive_skills__(self):
		tree = self.xml.find('Tree')
		active_spec = tree.findall('Spec')[int(tree.attrib['activeSpec'])-1]
		self.passives_url = active_spec.find('URL').text.strip()
		
		# parse out the base64 encoded string (stuff after the last /)
		b64 = re.search('[^/]+$', self.passives_url).group(0)
		# Replace all instances of - with + and all _ with /
		b64 = b64.replace('-', '+').replace('_', '/')
		# b64 decode it
		b = base64.b64decode(b64)
		
		if not b or len(b) < 6:
			raise Exception('The build\'s passive skill tree is invalid.')
		
		ver = ord(b[0]) * 16777216 + ord(b[1]) * 65536 + ord(b[2]) * 256 + ord(b[3])
		
		if ver > 4:
			raise Exception("The build's passive skill tree link uses an unknown version (number '{:s}').".format(ver))
			
		#nodes = b.replace(ver >= 4 and chr(8) or chr(7), chr(-1))
		nodes = b
		#logging.debug(nodes)
		
		self.passives_by_name = {}
		self.passives_by_id = {}
		
		for i in range(8, len(nodes)-1, 2):
			id = ord(nodes[i-1]) * 256 + ord(nodes[i])
			
			if id in passives.nodes:
				self.passives_by_name[passives.nodes[id]['dn']] = id
				self.passives_by_id[id] = True
			
		#logging.debug(allocNodes)
		
	def __parse_items__(self):
		self.items = {}
		
		xml_items = self.xml.find('Items')
		
		for i in xml_items.findall('Item'):
			self.items[int(i.attrib['id'])] = item_t(self, i)
			
		self.equipped_items = {}
			
		for slot in xml_items.findall('Slot'):
			# Skip inactive flasks
			# FIXME: Inactive flasks are technically equipped but this is a bit simpler than having
			# to worry about whether any item is "active" when only flasks have that property
			if "Flask" in slot.attrib['name'] and not ('active' in slot.attrib and slot.attrib['active'].lower() == "true"):
				continue
				
			self.equipped_items[slot.attrib['name']] = self.items[int(slot.attrib['itemId'])]
			self.equipped_items[slot.attrib['name']].slot = slot.attrib['name']
			
		# Jewels
		jewel_idx = 0
		for sock in self.xml.findall("Socket"):
			id = int(sock.attrib['itemId'])
			if id > 0:
				jewel_idx += 1;
				key = "Jewel{}".format(jewel_idx)
				self.equipped_items[key] = self.items[id]
				
				if self.equipped_items[key].slot is None:
					self.equipped_items[key].slot = key
					
		if xml_items.attrib['useSecondWeaponSet'].lower() == "true":
			self.active_weapon_set = 1
		else:
			self.active_weapon_set = 0
			
		#logging.debug(repr(self.equipped_items))
		
	def __check_build_eligibility__(self):
		if self.main_gem.is_supported_by("Cast on Critical Strike"):
			raise UnsupportedException('Cast on Critical Strike builds are currently not supported.')
	
	# Utility function for searching all equipped gear for a particular modifier.
	# Args:		A regex pattern that determines if a mod matches
	# Returns:	A list of match objects, one for each matching mod.
	def item_mod_search(self, pattern):
		pattern = pattern.lower()
		matches = []
			
		for key in self.equipped_items:
			item = self.equipped_items[key]
			for mod in item.mods:
				match_obj = re.search( pattern, mod.lower() )
				if match_obj is not None:
					matches.append(match_obj)
					
		return matches
		
	def get_class(self):
		if hasattr(self, 'ascendancy_name'):
			return self.ascendancy_name
			
		return self.class_name
		
	def has_passive_skill(self, skill):
		if isinstance(skill, int):
			return skill in self.passives_by_id
		elif isinstance(skill, str):
			return skill in self.passives_by_name
		else:
			raise Exception("has_passive_skill was passed an invalid param #2: {}".format(skill))
			
	def has_item_equipped(self, name):
		for i in self.equipped_items:
			if self.equipped_items[i].name.lower() == name.lower():
				if "Weapon" in i:
					if ( self.active_weapon_set == 1 and "Swap" in i ) or ( self.active_weapon_set == 0	and "Swap" not in i ):
						return True
				else:
					return True
				
		return False
		
	def get_stat(self, stat_name, minion=False):
		return self.stats['minion' if minion else 'player'][stat_name]
		
	def is_low_life(self):
		return self.get_stat('LifeUnreservedPercent') < 35

	def is_MoM(self):
		return self.has_passive_skill("Mind Over Matter") or self.has_item_equipped("Cloak of Defiance")
		
	# FIXME: Use values from the modifiers themselves instead of hardcoding.
	def get_MoM_percent(self):
		p = 0
		
		if self.is_MoM():
			p += 0.30
			
		if self.has_item_equipped("Cloak of Defiance"):
			p += 0.10
			
		if self.has_passive_skill("Divine Guidance"):
			p += 0.10
			
		return p

	def is_hybrid(self):
		if self.has_passive_skill("Chaos Inoculation"):
			return False
		
		if self.has_passive_skill("Eldritch Battery"):
			return False
		
		if self.is_low_life():
			return False
			
		return self.get_stat('EnergyShield') >= self.get_stat('LifeUnreserved') * 0.25
		
	def deals_minion_damage(self):
		return self.get_stat('TotalDPS', minion=True) > 0
		
	def get_main_descriptor(self):
		for unique in build_defining_uniques:
			if self.has_item_equipped(unique):
				if isinstance(build_defining_uniques[unique], str):
					return build_defining_uniques[unique]
				else:
					return unique
		
		return self.main_gem.name
		
	def get_totem_limit(self):
		tl = 1
		
		if self.has_passive_skill("Ancestral Bond"):
			tl += 1
			
		if self.has_passive_skill("Hierophant"): # Ascendant Hierophant
			tl += 1
		
		if self.has_passive_skill("Pursuit of Faith"):
			tl += 1
		
		if self.has_passive_skill("Ritual of Awakening"):
			tl += 1
		
		# Parse equipped items for ones that grant additional Totems
		matches = self.item_mod_search("Can have up to (\d+) additional Totems? summoned at a time")
		
		for match_obj in matches:
			tl += int(match_obj.group(1))
			
		return tl
		
	def show_average_damage(self):
		# Hack to override trap cooldown for certain traps in the 3.2-3.3 interim.
		if self.main_gem.is_trap():
			return True
		if self.main_gem.is_mine():
			return True
		if self.main_gem.is_vaal_skill() and self.main_gem.name != "Vaal Cyclone" and self.main_gem.name != "Vaal Righteous Fire":
			return True
		if self.main_gem.name == "Lightning Warp":
			return True
		if self.main_gem.name == "Molten Burst":
			return True
		if self.main_gem.item is not None:
			if self.main_gem.item.name == "Cospri's Malice" or self.main_gem.item.name == "The Poet's Pen" or self.main_gem.item.name == "Mjolner":
				return True
		if self.main_gem.is_supported_by("Cast when Damage Taken"):
			return True
			
		return False
		
	def show_dps(self):
		if self.main_gem.is_mine():
			return True
		if self.main_gem.is_trap() and self.get_stat("TrapCooldown") == 0:
			return True
		if self.show_average_damage():
			return False
		
		return True
		
	def get_bleed_dps(self):
		bleed = self.get_stat('BleedDPS')
		
		if self.has_passive_skill("Crimson Dance"):
			desc = "\n".join(passives.nodes[self.passives_by_name["Crimson Dance"]]['sd'])
			max_stacks = re.search("You can inflict Bleeding on an Enemy up to (\d+) times", desc).group(1)
			bleed *= int(max_stacks)
			
		return bleed
		
	def get_average_damage(self):
		damage = {}
		
		damage['direct'] = self.get_stat('AverageDamage')
		
		if self.get_stat('WithPoisonAverageDamage') > 0:
			# If "WithPoisonAverageDamage" is available, then use that for simplicity.
			damage['poison'] = self.get_stat('WithPoisonAverageDamage') - damage['direct']
		elif self.get_stat('WithPoisonDPS') > 0:
			# Otherwise we need to do something janky because only average damage skills have WPAD, and "PoisonDamage"
			# doesn't account for poison chance which also isn't in the XML.
			# Solution: Since its not an avg dmg skill it that means its a DPS skill and it should include the 
			# "WithPoisonDPS" stat. Divide by speed to find the poison damage.
			damage['poison'] = ( self.get_stat('WithPoisonDPS') - self.get_stat('TotalDPS') ) / self.get_stat('Speed')
		else:
			damage['poison'] = 0.000
		
		return damage
		
	def get_speed_multiplier(self):
		sm = 1.000
		
		if self.main_gem.is_mine():
			sm *= self.main_gem.get_num_mines_laid()
			
		if self.main_gem.is_trap():
			sm *= self.main_gem.get_num_traps_thrown()
				
		return sm
		
	def get_speed(self, minion=False):
		speed = self.get_stat('Speed', minion=minion)
	
		if self.main_gem.is_mine():
			speed = 1 / float(self.get_stat('MineLayingTime'))
		if self.main_gem.is_trap():
			speed = 1 / float(self.get_stat('TrapThrowingTime'))
			
		speed *= self.get_speed_multiplier()
		
		return speed
		
	def get_speed_str(self):
		if self.deals_minion_damage():
			'''
			If its minion damage, I have no idea how to properly figure out
			whether something is an attack or spell. So just default to "use"
			even though its less than ideal. Better to show "use" than no speed
			at all.
			'''
			return "Use/sec"
		if self.main_gem.is_mine():
			return "Mines/sec"
		elif self.main_gem.is_trap():
			return "Traps/sec"
		elif self.main_gem.is_attack():
			return "Attacks/sec"
		elif self.main_gem.is_spell():
			return "Casts/sec"
		else:
			return "Use/sec"
			
	@staticmethod
	def stat_sort(element):
		return element[0]
		
	def get_dps_breakdown(self):
		if self.deals_minion_damage():
			if self.get_stat('ActiveMinionLimit') > 1:
				return [
					(self.get_stat('TotalDPS', minion=True) * self.get_stat('ActiveMinionLimit'), "total DPS"),
					(self.get_stat('TotalDPS', minion=True), "DPS per minion"),
				]
			else:
				return [ (self.get_stat('TotalDPS', minion=True), "DPS") ]
		else:
			damage = {}
			stats = []
			
			if self.show_average_damage():
				damage = self.get_average_damage()
				
				total = damage['direct'] + damage['poison']
						
				if damage['poison'] >= 0.05 * total:
					stats.append( ( total, "total dmg" ) )
					stats.append( ( damage['poison'], "poison dmg" ) )
				else:
					stats.append( ( total, "avg damage" ) )
				
				ignite = self.get_stat('IgniteDPS')
				
				if ignite * 4 >= 0.05 * total:
					stats.append( ( ignite, "ignite DPS" ) )
				
			if self.show_dps():
				dps = {}
				
				# new list for dps stats so we can sort it independently of average damage stats
				dps_stats = []
				
				# if this skill is an average damage skill
				if len(damage) > 0:
					# then calculate the DPS using average damage times speed
					speed = self.get_speed()
					dps['direct'] = damage['direct'] * speed
					dps['poison'] = damage['poison'] * speed
				else:
					# otherwise just use the DPS stats
					dps['direct'] = self.get_stat('TotalDPS')
					if self.get_stat('WithPoisonDPS') > 0:
						# For some reason WithPoisonDPS also includes skill DoT DPS
						dps['poison'] = self.get_stat('WithPoisonDPS') - dps['direct'] - self.get_stat('TotalDot')
					else:
						dps['poison'] = 0.000
				
				'''skill_hit_multiplier = self.get_stat('TotalDPS') / dps['direct']
				dps['direct'] *= skill_hit_multiplier
				dps['poison'] *= skill_hit_multiplier'''
				
				dps['skillDoT'] = self.get_stat('TotalDot')
				dps['bleed'] = self.get_bleed_dps()
				dps['ignite'] = self.get_stat('IgniteDPS')
				dps['decay'] = self.get_stat('DecayDPS')
				
				# skill specific override
				if self.main_gem.name == "Essence Drain":
					if dps['poison'] <= 0.000:
						dps['direct'] = 0.000
						dps['ignite'] = 0.000
				
				if self.main_gem.is_totem() and self.main_gem.get_totem_limit() > 1:
					# assume skill DoT stacks
					per_totem = dps['direct'] + dps['poison']
					
					dot_stacks = self.main_gem.has_stackable_dot()
					
					if dot_stacks:
						per_totem += dps['skillDoT']
						
					dps_stats.append( ( per_totem, " DPS per totem" ) )
					
					totem_limit = self.get_totem_limit()
					dps['direct'] *= totem_limit
					dps['poison'] *= totem_limit
					
					if dot_stacks:
						dps['skillDoT'] *= totem_limit
						
				total = sum(dps.values())
				
				# only show DoTs in breakdown if, together, they add up to a meaningful amount of DPS
				if dps['direct'] < 0.95 * total:
					# Base DoT -- only show if its not the sole source of damage
					if dps['skillDoT'] > 0.01 * total and total != dps['skillDoT']:
						dps_stats.append( ( dps['skillDoT'], "skill DoT DPS" ) )
						
					# Poison
					if dps['poison'] > 0.01 * total:
						dps_stats.append( ( dps['poison'], "poison DPS" ) )
					
					# Bleed
					if dps['bleed'] > 0.01 * total:
						dps_stats.append( ( dps['bleed'], "bleed DPS" ) )
						
					# Ignite
					if dps['ignite'] > 0.01 * total:
						dps_stats.append( ( dps['ignite'], "ignite DPS" ) )
						
					# Decay
					if dps['decay'] > 0.01 * total:
						dps_stats.append( ( dps['decay'], "decay DPS" ) )
						
					# sort stats descending
					if len(dps_stats) > 1:
						dps_stats.sort(key=build_t.stat_sort, reverse=True)
				
				if len(dps_stats) > 0:
					dps_stats.insert(0, ( total, "total DPS" ))
				else:
					dps_stats.insert(0, ( total, "DPS" ))
				
				# combine DPS stats and average damage stats into one list
				dps_stats.extend(stats)
				stats = dps_stats
				
		return stats
		
				
	def get_enabled_gem(self, gem_name):
		for gem in self.xml.findall("./Skills/Skill/Gem[@nameSpec='{}']".format(gem_name)):
			if "enabled" in gem.attrib and gem.attrib['enabled'].lower() == "true":
				return gem
				
		return None
		
	def __get_config_value__(self, name):
		xml_input = self.xml_config.find("*[@name='{:s}']".format(name))
		
		if xml_input is None:
			logging.log(logger.DEBUG_ALL, "CONFIG {:s}: {:s}".format(name, None))
			return None
			
		if 'boolean' in xml_input.attrib:
			logging.log(logger.DEBUG_ALL, "CONFIG {:s}: {:s}".format(name, xml_input.attrib['boolean'].lower()))
			return xml_input.attrib['boolean'].lower()
			
		if 'number' in xml_input.attrib:
			logging.log(logger.DEBUG_ALL, "CONFIG {:s}: {:n}".format(name, float(xml_input.attrib['number'])))
			return float(xml_input.attrib['number'])
			
		if 'string' in xml_input.attrib:
			logging.log(logger.DEBUG_ALL, "CONFIG {:s}: {:s}".format(name, xml_input.attrib['string'].lower()))
			return xml_input.attrib['string'].lower()
			
	def __get_config_array__(self):
		dps_config = []
	
		if self.__get_config_value__("enemyIsBoss") == "true":
			dps_config.append("Boss")
		elif self.__get_config_value__("enemyIsBoss") == "shaper":
			dps_config.append("Shaper")
		
		for opt_name in self.config_bools:
			if self.__get_config_value__(opt_name) == "true":
				dps_config.append(self.config_bools[opt_name])
		
		for opt_name in self.config_numbers:
			val = self.__get_config_value__(opt_name)
			if val and val != 0:
				dps_config.append(self.config_numbers[opt_name].format(val))
				
		for opt_name in self.config_strs:
			val = self.__get_config_value__(opt_name)
			if val and not isinstance(val, float):
				dps_config.append(self.config_strs[opt_name].format(val.title()))
				
		if self.get_enabled_gem("Vaal Haste") is not None:
			dps_config.append("Vaal Haste")
				
		wither = self.get_enabled_gem("Wither")
		if wither is not None:
			dps_config.append("Wither \({}\)".format(self.wither_stacks[wither.attrib['skillPart']]))
				
		if self.get_enabled_gem("Punishment") is not None:
			dps_config.append("Punishment")
				
		logging.debug("DPS config: {}".format(dps_config))
		
		return dps_config
			
	def __get_config_string__(self):
		dps_config = self.__get_config_array__()
		
		if len(dps_config) == 0:
			return ""
		
		return "  \n\n" + " **Config:** {:s}".format(", ".join(dps_config)).replace(' ', " ^^")
		
	def is_fully_geared(self):
		# Universally required slots
		required_slots = [
			"Helmet",
			"Body Armour",
			"Gloves",
			"Boots",
			"Amulet",
			"Ring 1",
			"Ring 2",
			"Belt",
		]
		
		# Ignore off-hand slot because I currently don't have any
		# good way of determining whether a weapon is a two-hander.
		
		# Add required weapon slots based on which weapon swap is active
		if self.active_weapon_set == 0:
			#required_slots += [ "Weapon 1" , "Weapon 2" ]
			required_slots += [ "Weapon 1" ]
		else:
			#required_slots += [ "Weapon 1 Swap", "Weapon 2 Swap" ]
			required_slots += [ "Weapon 1 Swap" ]
				
		# Remove some required slots if specific uniques are equipped
		
		'''
		if self.has_item_equipped("White Wind"):
			if "Weapon 2" in required_slots:
				required_slots.remove("Weapon 2")
			if "Weapon 2 Swap" in required_slots:
				required_slots.remove("Weapon 2 Swap")
		'''
			
		if self.has_item_equipped("Facebreaker"):
			if "Weapon 1" in required_slots:
				required_slots.remove("Weapon 1")
			if "Weapon 1 Swap" in required_slots:
				required_slots.remove("Weapon 1 Swap")
			
		if self.has_item_equipped("Bringer of Rain"):
			required_slots.remove("Body Armour")
			
		if self.has_item_equipped("Thief's Torment"):
			required_slots.remove("Ring 1")
			required_slots.remove("Ring 2")
		
		slots_filled = 0
		
		for slot in required_slots:
			if slot in self.equipped_items:
				slots_filled += 1
				
		return slots_filled >= len(required_slots)
		
	def get_response(self):
		response = self.get_response_header()
		response += self.get_response_body()
		#response += self.get_response_footer()
		
		return response.replace('\n', '  \n')
		
	def get_response_header(self):
		# Defense descriptor
		def_desc = ""
		if self.has_passive_skill("Chaos Inoculation"):
			def_desc = "CI"
		elif self.is_MoM():
			def_desc = "MoM"
		elif self.is_low_life():
			def_desc = "LL"
			
		if self.is_hybrid():
			if def_desc != "":
				def_desc = " " + def_desc
			def_desc = "Hybrid" + def_desc
			
		#if def_desc == "":
		#	def_desc = "Life"
		
		# Crit descriptor
		crit_desc = ""
		if self.get_stat("CritChance") >= 20 and not self.has_passive_skill("Elemental Overload"):
			crit_desc = " Crit"
		
		# Skill Descriptor
		gem_name = self.get_main_descriptor()
		
		# Totem/Trap/Mine Descriptor
		actor_desc = ''
		
		if self.main_gem.is_supported_by("Spell Totem") or self.main_gem.is_supported_by("Ranged Attack Totem"):
			actor_desc = " Totem"
		elif self.main_gem.is_supported_by("Remote Mine"):
			actor_desc = " Mine"
		elif self.main_gem.is_supported_by("Trap"):
			actor_desc = " Trap"
		
		header = "###[{:s}{:s} {:s}{:s} {:s}]({:s})\n".format( def_desc, crit_desc, gem_name, actor_desc, self.get_class(), self.pastebin.url )
		
		# Passive Skill Tree
			
		line2 = "^(Level {:n}) ^[(Tree)]({:s})".format(self.level, self.passives_url)
		
		# pob.party link
		try:
			web_pob = pob_party.get_url(self.pastebin)
			line2 += " [^((Open in Browser)^)]({:s})".format(web_pob)
		except PoBPartyException:
			logging.warning("Failed to get pob party url for {}.".format(self.pastebin.key))
			pass
			
		# author
		line2 += " ^(| by {:s})\n*****\n".format(self.author)
		
		if hasattr(self, 'ascendancy_name'):
			line2 = "[](#{:s}) ".format(self.ascendancy_name.lower()) + line2
			
		header += line2
		
		#logging.debug(header)
		return header
	
	def get_response_body(self):
		body = ""
		
		# First line (EHP stuff)
		
		total_ehp = 0;
		show_ehp = False
		
		if self.has_passive_skill("Chaos Inoculation"):
			if self.is_fully_geared():
				body = "{:n} **ES**".format(self.get_stat('EnergyShield'))
				total_ehp += self.get_stat('EnergyShield')
			else:
				body = "{:n}% **ES**".format(self.get_stat("Spec:EnergyShieldInc"))
		else:
			if self.is_fully_geared() and self.level > 1:
				body = "{:n} **Life**".format(self.get_stat('LifeUnreserved'))
				total_ehp += self.get_stat('LifeUnreserved')
			else:
				body = "{:n}% **Life**".format(self.get_stat("Spec:LifeInc"))
			
			if self.is_MoM():
				if self.is_fully_geared() and self.level > 1:
					# Display the full amount of unreserved mana
					body += " | {:n} **Mana**".format(self.get_stat('ManaUnreserved'))
					
					if self.has_passive_skill("Eldritch Battery"):
						body += " | {:n} **ES**".format(self.get_stat('EnergyShield'))
					
					# Calculate the maximum amount of mana that contributes to the player's EHP
					mom_pct = self.get_MoM_percent()
					max_ehp_mana = self.get_stat('LifeUnreserved') * ( mom_pct / ( 1 - mom_pct ) )
					
					eff_max_mana = self.get_stat('ManaUnreserved')
					
					if self.has_passive_skill("Eldritch Battery"):
						eff_max_mana += self.get_stat('EnergyShield')
					
					# Add up to the max amount
					total_ehp += int( min( eff_max_mana, max_ehp_mana ) )
					
					show_ehp = True
				else:
					body += " | {:n}% **Mana**".format(self.get_stat("Spec:ManaInc"))
				
			if self.is_hybrid() or self.is_low_life():
				if self.is_fully_geared():
					body += " | {:n} **ES**".format(self.get_stat('EnergyShield'))
					total_ehp += self.get_stat('EnergyShield')
					show_ehp = True
				else:
					body += " | {:n}% **ES**".format(self.get_stat("Spec:EnergyShieldInc"))
		
		if show_ehp:
			body += " | {:n} **total** **EHP**".format(total_ehp)
		
		body = '^' + body.replace(' ', ' ^') + "\n"
		
		# Second line (defenses)
		
		line = ""
		
		if self.get_stat('MeleeEvadeChance') >= 15:
			line += "{:.0f}% **Evade**".format(self.get_stat('MeleeEvadeChance'))
		
		if self.get_stat('PhysicalDamageReduction') >= 10:
			if line != "":
				line += " | "
			line += "{:n}% **Phys** **Mitg**".format(self.get_stat('PhysicalDamageReduction'))
		
		if self.get_stat('BlockChance') >= 30:
			if line != "":
				line += " | "
			line += "{:n}% **Block**".format(self.get_stat('BlockChance'))
		
		if self.get_stat('SpellBlockChance') > 0:
			if line != "":
				line += " | "
			line += "{:.0f}% **Spell** **Block**".format(self.get_stat('SpellBlockChance'))
		
		if self.get_stat('AttackDodgeChance') > 3:
			if line != "":
				line += " | "
			line += "{:n}% **Dodge**".format(self.get_stat('AttackDodgeChance'))
		
		if self.get_stat('SpellDodgeChance') > 3:
			if line != "":
				line += " | "
			line += "{:n}% **Spell** **Dodge**".format(self.get_stat('SpellDodgeChance'))
		
		if line != "":
			line = '^' + line.replace(' ', ' ^') + '\n'
			body += line
		
		body += "\n"
		
		## Offense
		num_supports = self.main_gem.get_num_support_gems()
		
		if num_supports < 3 and not ( self.main_gem.item is not None and ( self.main_gem.item.name == "Cospri's Malice" or self.main_gem.item.name == "The Poet's Pen" or self.main_gem.item.name == "Mjolner" ) ):
			raise EligibilityException('Active skill {} has only {} support gem, it must have at least 3 support gems. {}'.format( self.main_gem.name, num_supports, ERR_CHECK_ACTIVE_SKILL ) )

		dps_breakdown = self.get_dps_breakdown()
		
		if dps_breakdown[0][0] <= 0:
			raise EligibilityException('Active skill {:s} does no DPS! {:s} {}'.format( self.main_gem.name, repr(dps_breakdown), ERR_CHECK_ACTIVE_SKILL ))
		elif dps_breakdown[0][0] < 500:
			raise EligibilityException('Active skill {:s} does negligible DPS! {:s} ()'.format( self.main_gem.name, repr(dps_breakdown), ERR_CHECK_ACTIVE_SKILL ))
		
		dps_str = ""
		
		for b in dps_breakdown:
			if dps_str != "":
				dps_str += " | "
				
			dps_str += "{:s} {:s}".format(util.floatToSigFig(b[0]), b[1])
			
		body += "**{:s}** {:s} *({:n}L)* - *{:s}*".format(self.main_gem.name, self.main_gem.get_support_gem_str(), 1+num_supports, dps_str) + '  \n'
		
		pieces = []
		
		if self.deals_minion_damage():
			# Minion speed str
			pieces.append("{:.2f} **{}**".format(self.get_speed(minion=True), self.get_speed_str()))
		else:
			# Add a speed str as long as the skill is not instant cast.
			if not (self.main_gem.data.cast_time is not None and self.main_gem.data.cast_time == 0):
				# FIXME: ugly support for CwDT cd
				if self.main_gem.is_supported_by("Cast when Damage Taken"):
					pieces.append("{:.2f}s **CD**".format(self.get_stat("Cooldown")))
				else:
					pieces.append("{:.2f} **{}**".format(self.get_speed(), self.get_speed_str()))
		
		if self.main_gem.is_totem():
			pieces.append("{} **Totems**".format(self.main_gem.get_totem_limit()))
		
		if self.get_stat('CritChance') >= 20 and not self.has_passive_skill("Elemental Overload"):
			pieces.append("{:.2f}% **Crit**".format(self.get_stat('CritChance')))
			pieces.append("{:n}% **Multi**".format(self.get_stat('CritMultiplier')*100))
			
		if self.main_gem.is_trap() and self.get_stat("TrapCooldown") > 0:
			pieces.append("{:.2f}s **Cooldown**".format(self.get_stat("TrapCooldown")))
		
		if len(pieces) > 0:
			line = " | ".join(pieces)
			body += '^' + line.replace(' ', ' ^')
		
		body += self.__get_config_string__()
		
		#logging.debug(body)
		return body