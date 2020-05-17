# Python
import base64
import re
import logging
import math

# 3rd Party
import praw.models
import defusedxml.ElementTree as ET

# Self
import util
import logger
import pob_party
import passive_skill_tree as passives
from name_overrides import build_defining_uniques
from gem import gem_t
import stat_parsing
from item import make_item

from _exceptions import UnsupportedException
from _exceptions import GemDataException
from _exceptions import EligibilityException
from _exceptions import PoBPartyException
from _exceptions import StatWhitelistException

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
			"ImpaleDPS",
			"WithImpaleDPS",
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

		self.enabled = True

		if 'enabled' in self.xml.attrib:
			self.enabled = self.xml.attrib['enabled'].lower() == 'true'
		
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
			if not gem.enabled:
				continue

			if not gem.data.is_support:
				current_skill += 1

			if gem.data_2 is not None and not gem.data_2.is_support:
				current_skill += 1
		
			if current_skill >= n:
				return gem
					
		if current_skill > 1:
			raise Exception('mainActiveSkill exceeds total number of active skill gems in socket group.')
		else:
			raise EligibilityException('Active skill group contains no active skill gems. {}'.format(ERR_CHECK_ACTIVE_SKILL))
			
	def get_active_gem(self):
		if self.active_skill == 0:
			return False
	
		return self.get_gem_of_nth_active_skill(self.active_skill)

	def find_skill(self, skill_name, enabled=False):
		for gem in self.gems:
			if gem.has_skill(skill_name, enabled=enabled):
				return gem

		return None

class build_t:
	config_bools = {
		"conditionFullLife": "Full Life",
		"conditionKilledRecently": "Killed Recently",
		"conditionEnemyMoving": "Enemy Moving",
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
	}
	
	config_strs = {
		#"waveOfConvictionExposureType": "{} Exposure",
	}
	
	# Dict of Wither Stacks by its corresponding skillPart
	wither_stacks = {
		"1": 1,
		"2": 5, 
		"3": 10,
		"4": 15,
	}
	
	def __init__(self, importer, author, praw_object):
		self.xml = importer.xml()
		self.xml_build = self.xml.find('Build')
		self.xml_config = self.xml.find('Config')
		self.importer = importer
		self.praw_object = praw_object
		
		self.__parse_passive_skills__()
		self.__parse_items__()
		self.__parse_author__(author)
		self.__parse_stats__()
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
		
		self.__parse_socket_groups__()
		self.__parse_main_gem__()
		
	def __parse_socket_groups__(self):
		skills = self.xml.find('Skills')

		if len(skills) == 0:
			raise EligibilityException('Build has no active skills.')

		self.socket_groups = []

		for group_xml in skills:
			sg = socket_group_t(group_xml, self)
			self.socket_groups.append(sg)
		
	def __parse_main_gem__(self):
		if self.get_main_socket_group() is None:
			self.__parse_socket_groups__()
		
		self.main_gem = self.get_main_socket_group().get_active_gem()
		
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
					value = stat.attrib['value']

					if value == 'nan':
						self.stats[key][stat.attrib['stat']] = 0
					else:
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
				self.passives_by_name[passives.nodes[id]['name']] = id
				self.passives_by_id[id] = True

		# parse cluster jewel nodes
		for node_id in active_spec.attrib['nodes'].split(','):
			node_id = int(node_id)

			if node_id < 65536:
				# non-cluster jewel node
				# just sanity check that we already processed it
				if node_id not in self.passives_by_id:
					logging.debug("{} ({}) was excluded from tree data!".format(passives.nodes[node_id]['name'], node_id))
					self.passives_by_id[node_id] = True
			else:
				# cluster passive
				# just flag it as allocated, the black magic determining what
				# the passive actually is is handled in item_cluster_jewel.py
				self.passives_by_id[node_id] = True

		
	def __parse_items__(self):
		logging.debug("{} parses items.".format(self.importer.key))

		self.items = {}
		
		xml_items = self.xml.find('Items')
		
		for i in xml_items.findall('Item'):
			self.items[int(i.attrib['id'])] = make_item(self, i)
			
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

		for sock in self.xml.findall('Tree/Spec/Sockets/Socket'):
			id = int(sock.attrib['itemId'])
			node_id = int(sock.attrib['nodeId'])

			if id > 0 and node_id in self.passives_by_id:
				jewel_idx += 1;
				key = "Jewel{}".format(jewel_idx)

				#logging.info("{} equips jewel ({}) {} {}.".format(self.importer.key, id, self.items[id].name, self.items[id].base))

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

		if self.__get_config_value__("conditionEnemyShocked") == "true":
			val = self.__get_config_value__("conditionShockEffect")

			if val is not None:
				dps_config.append("Shock \({:n}%\)".format(val))
			else:
				dps_config.append("Shock \(50%\)")
		
		for opt_name in self.config_bools:
			if self.__get_config_value__(opt_name) == "true":
				dps_config.append(self.config_bools[opt_name])
		
		for opt_name in self.config_numbers:
			val = self.__get_config_value__(opt_name)
			if val and val != 0:
				dps_config.append(self.config_numbers[opt_name].format(val))

		if self.find_skill("Aspect of the Spider", enabled=True) is not None:
			val = self.__get_config_value__("aspectOfTheSpiderWebStacks")
			if val and val != 0:
				dps_config.append("Spider's Web \({:n}\)".format(val))
				
		for opt_name in self.config_strs:
			val = self.__get_config_value__(opt_name)
			if val and not isinstance(val, float):
				dps_config.append(self.config_strs[opt_name].format(val.title()))

		if self.find_skill("Wave of Conviction", enabled=True) is not None:
			val = self.__get_config_value__("waveOfConvictionExposureType")
			if val is not None and isinstance(val, str):
				dps_config.append("{} Exposure".format(val.title()))
				
		if self.find_skill("Vaal Haste", enabled=True) is not None:
			dps_config.append("Vaal Haste")

		if self.main_gem.is_spell():
			vrf_gem = self.find_skill("Vaal Righteous Fire", enabled=True)

			if vrf_gem is not None and vrf_gem != self.main_gem:
				dps_config.append("Vaal RF")

		if self.main_gem.is_attack():
			vaw_gem = self.find_skill("Vaal Ancestral Warchief", enabled=True)

			if vaw_gem is not None and vaw_gem != self.main_gem:
				dps_config.append("Vaal Warchief")
				
			if self.find_skill("Punishment", enabled=True) is not None:
				dps_config.append("Punishment")
				
		wither_gem = self.find_skill("Wither", enabled=True)

		if wither_gem is not None:
			# LocalIdentity Fork implementation:
			# wither stacks is a config option
			wither_stacks = self.__get_config_value__('multiplierWitheredStackCount')

			# Openarl implementation:
			# wither has skill parts that refer to a stack count
			if wither_stacks is None and 'skillPart' in wither_gem.xml.attrib:
				wither_stacks = self.wither_stacks[wither_gem.xml.attrib['skillPart']]

			if wither_stacks is not None:
				dps_config.append("Wither \({}\)".format(int(wither_stacks)))
				
		logging.debug("DPS config: {}".format(dps_config))
		
		return dps_config
			
	def __get_config_string__(self):
		dps_config = self.__get_config_array__()
		
		if len(dps_config) == 0:
			return ""
		
		return "  \n\n" + " **Config:** {:s}".format(", ".join(dps_config)).replace(' ', " ^^")

	def get_main_socket_group(self):
		msg_index = int(self.xml_build.attrib['mainSocketGroup'])

		msg = self.socket_groups[msg_index-1]
		
		# check to make sure main socket group is not in an inactive weapon set
		if 'slot' in msg.xml.attrib and "Weapon" in msg.xml.attrib['slot']:
			useSecondWeaponSet = self.xml.find('Items').attrib['useSecondWeaponSet'].lower() == "true"
			slot = msg.xml.attrib['slot']
			
			if ( not useSecondWeaponSet and "Swap" in slot ) or ( useSecondWeaponSet and "Swap" not in slot ):
				raise EligibilityException('The active skill gem is socketed in an inactive weapon (ie weapon swap).')

		return msg
		
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

	def has_keystone(self, keystone):
		# check if the passive skill is allocated
		if self.has_passive_skill(keystone):
			return True

		# use stat parsing to identify any items that grant a stat which grants the keystone
		if keystone in stat_parsing.keystone_map:
			# get the list of stats that grant the specified keystone
			# usually only 1 stat but in some cases its more
			keystone_stats = stat_parsing.keystone_map[keystone]

			for item in self.equipped_items.values():
				for keystone_stat in keystone_stats:
					if keystone_stat in item.stats.dict():
						return True

		return False

	def get_stat_total(self, stat):
		if stat not in stat_parsing.whitelist:
			raise StatWhitelistException("'{}' not in whitelist".format(stat))

		total = 0

		for item in self.equipped_items.values():
			d = item.stats.dict()

			if stat in d:
				total += d[stat]

		logging.log(logger.DEBUG_ALL, "'{}': {}".format(stat, total))
		return total

	def get_item(self, name, equipped_only=False):
		# prefer equipped items
		for t in self.equipped_items.items():
			slotName = t[0]
			item = t[1]

			if item.name.lower() == name.lower():
				if "Weapon" in slotName:
					if ( self.active_weapon_set == 1 and "Swap" in slotName ) or ( self.active_weapon_set == 0	and "Swap" not in slotName ):
						return item
				else:
					return item

		if not equipped_only:
			for item in self.items.values():
				if item.name.lower() == name.lower():
					return item
				
		return None
			
	def has_item_equipped(self, name):
		return self.get_item(name, equipped_only=True) is not None
		
	def get_stat(self, stat_name, minion=False):
		return self.stats['minion' if minion else 'player'][stat_name]
		
	def is_low_life(self):
		return self.get_stat('LifeUnreservedPercent') < 35
		
	# FIXME: Use values from the modifiers themselves instead of hardcoding.
	def get_MoM_percent(self):
		p = 0
		
		if self.has_keystone("Mind Over Matter"):
			p += 0.30

		if self.has_passive_skill("Divine Guidance"):
			p += 0.10
			
		'''	
		if self.has_item_equipped("Cloak of Defiance"):
			p += 0.10
		'''	
		
		p += self.get_stat_total('base_damage_removed_from_mana_before_life_%') / 100

		if self.find_skill('Clarity', enabled=True) or self.find_skill('Vaal Clarity', enabled=True):
			p += self.get_stat_total('damage_removed_from_mana_before_life_%_while_affected_by_clarity') / 100
			
		return p

	def is_hybrid(self):
		if self.has_keystone("Chaos Inoculation"):
			return False
		
		if self.has_keystone("Eldritch Battery"):
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
		
		if self.has_keystone("Ancestral Bond"):
			tl += 1
			
		if self.has_passive_skill("Hierophant"): # Ascendant Hierophant
			tl += 1
		
		if self.has_passive_skill("Pursuit of Faith"):
			tl += 1
		
		# Account for items that grant additional totems
		# eg '+1 to maximum number of Summoned Totems'
		tl += self.get_stat_total('base_number_of_totems_allowed')
			
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
		if self.main_gem.name == "Shockwave":
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
		
		if self.has_keystone("Crimson Dance"):
			desc = "\n".join(passives.nodes[self.passives_by_name["Crimson Dance"]]['stats'])
			max_stacks = re.search("You can inflict Bleeding on an Enemy up to (\d+) times", desc).group(1)
			bleed *= int(max_stacks)
			
		return bleed
		
	def get_average_damage(self):
		damage = {}
		
		damage['direct'] = self.get_stat('AverageDamage')
		
		if self.get_stat('WithPoisonAverageDamage') > 0:
			# If "WithPoisonAverageDamage" is available, then use that for simplicity.
			damage['poison'] = self.get_stat('WithPoisonAverageDamage')

			# subtract the direct damage
			damage['poison'] -= damage['direct']

			# subtract the skill DoT DPS, if any. This is very counterintuitively included in WPAD.
			# probably a PoB bug
			# This is gonna break whenever the bug is fixed in PoB.
			damage['poison'] -= self.get_stat('TotalDot')
		elif self.get_stat('WithPoisonDPS') > 0:
			# Otherwise we need to do something janky because only average damage skills have WPAD, and "PoisonDamage"
			# doesn't account for poison chance which also isn't in the XML.
			# Solution: Since its not an avg dmg skill it that means its a DPS skill and it should include the 
			# "WithPoisonDPS" stat. Divide by speed to find the poison damage.
			damage['poison'] = ( self.get_stat('WithPoisonDPS') - self.get_stat('TotalDPS') ) / self.get_stat('Speed')
		else:
			damage['poison'] = 0.000

		if self.get_stat('ImpaleDPS') > 0:
			damage['impale'] = self.get_stat('ImpaleDPS') / self.get_stat('Speed')
		else:
			damage['impale'] = 0.000
		
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
			Relatively decent method of detecting minion type. If the minion
			uses exclusively spells or attacks we can figure it out from its
			minion_type attributes. If it uses both (or neither?) then who
			knows and just put 'use' instead.
			'''
			if self.main_gem.is_attack_minion():
				return "Attacks/sec"
			elif self.main_gem.is_spell_minion():
				return "Casts/sec"
			else:
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
				
				total = damage['direct'] + damage['poison'] + damage['impale']

				avg_stats = []
						
				if damage['poison'] >= 0.05 * total:
					avg_stats.append( ( damage['poison'], "poison dmg" ) )

				if damage['impale'] >= 0.05 * total:
					avg_stats.append( ( damage['impale'], "impale dmg" ) )

				if len(avg_stats) > 0:
					avg_stats.append( ( total, "total dmg" ) )
				else:
					avg_stats.append( ( total, "avg damage" ) )
				
				ignite = self.get_stat('IgniteDPS')
				skillDoT = self.get_stat('TotalDot') # skill DoT DPS
				
				if ignite * 4 >= 0.05 * total:
					avg_stats.append( ( ignite, "ignite DPS" ) )
				
				if skillDoT >= 0.05 * total:
					avg_stats.append( ( skillDoT, "skill DoT DPS" ) )
				
				# combine average damage stats into main list
				stats.extend(avg_stats)
				
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
					dps['impale'] = damage['impale'] * speed
				else:
					# otherwise just use the DPS stats
					dps['direct'] = self.get_stat('TotalDPS')

					if self.get_stat('WithPoisonDPS') > 0:
						# For some reason WithPoisonDPS also includes skill DoT DPS
						dps['poison'] = self.get_stat('WithPoisonDPS') - dps['direct'] - self.get_stat('TotalDot')
					else:
						dps['poison'] = 0.000

					if self.get_stat('WithImpaleDPS') > 0:
						# Dec 12 2019
						# TotalDot is not included in "WithImpaleDPS" in the LocalIdentity fork
						# see Modules\CalcOffence-3_0.lua:2224
						# (the only fork that implements impale DPS calculations)
						dps['impale'] = self.get_stat('WithImpaleDPS') - dps['direct']
					else:
						dps['impale'] = 0.000
				
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

				for entry in dps.items():
					if entry[1] < 0:
						logging.debug("!!! DANGER WILL ROBINSON !!! {} DPS is negative ({:.2f} DPS). Overriding to 0...".format(entry[0], entry[1]))
						dps[entry[0]] = 0.000
				
				if self.main_gem.is_totem() and self.main_gem.get_totem_limit() > 1:
					per_totem = dps['direct'] + dps['poison'] + dps['impale']
					
					dot_stacks = self.main_gem.has_stackable_dot()
					
					if dot_stacks:
						per_totem += dps['skillDoT']
						
					dps_stats.append( ( per_totem, " DPS per totem" ) )
					
					totem_limit = self.main_gem.get_totem_limit()
					dps['direct'] *= totem_limit
					dps['poison'] *= totem_limit
					dps['impale'] *= totem_limit
					
					if dot_stacks:
						dps['skillDoT'] *= totem_limit
						
				total = sum(dps.values())
				
				# only show DoTs in breakdown if, together, they add up to a meaningful amount of DPS
				if dps['direct'] < 0.95 * total:
					# Base DoT -- only show if its not the sole source of damage
					# don't add it if it's already been added in the average damage block above
					if "skill DoT DPS" not in map(lambda s: s[1], stats):
						if dps['skillDoT'] > 0.01 * total and total != dps['skillDoT']:
							dps_stats.append( ( dps['skillDoT'], "skill DoT DPS" ) )
						
					# Poison
					if dps['poison'] > 0.01 * total:
						dps_stats.append( ( dps['poison'], "poison DPS" ) )

					# Impale
					if dps['impale'] > 0.01 * total:
						dps_stats.append( ( dps['impale'], "impale DPS" ) )
					
					# Bleed
					if dps['bleed'] > 0.01 * total:
						dps_stats.append( ( dps['bleed'], "bleed DPS" ) )
						
					# Ignite
					# don't add it if it's already been added in the average damage block above
					if "ignite DPS" not in map(lambda s: s[1], stats):
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
				
	def find_skill(self, skill_name, enabled=False):
		for sg in self.socket_groups:
			if enabled and not sg.enabled:
				continue

			gem = sg.find_skill(skill_name, enabled=enabled)

			if gem is not None:
				return gem
				
		return None
		
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

		if self.has_item_equipped("Facebreaker") or self.has_passive_skill("Hollow Palm Technique"):
			if "Weapon 1" in required_slots:
				required_slots.remove("Weapon 1")
			if "Weapon 1 Swap" in required_slots:
				required_slots.remove("Weapon 1 Swap")

		if self.has_passive_skill("Hollow Palm Technique"):
			required_slots.remove("Gloves")
			
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
		if self.has_keystone("Chaos Inoculation"):
			def_desc = "CI"
		elif self.has_keystone("Mind Over Matter"):
			if self.has_keystone("Eldritch Battery"):
				def_desc = "EB MoM"
			else:
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
		if self.get_stat("CritChance") >= 20 and not self.has_keystone("Elemental Overload"):
			crit_desc = " Crit"
		
		# Skill Descriptor
		gem_name = self.get_main_descriptor()
		
		# Totem/Trap/Mine Descriptor
		actor_desc = ''
		
		if self.main_gem.is_supported_by("Spell Totem") or self.main_gem.is_supported_by("Ballista Totem"):
			actor_desc = " Totem"
		elif self.main_gem.is_supported_by("Blastchain Mine") or self.main_gem.is_supported_by("High-Impact Mine"):
			actor_desc = " Mine"
		elif self.main_gem.is_supported_by("Trap"):
			actor_desc = " Trap"
		
		header = "###[{:s}{:s} {:s}{:s} {:s}]({:s})\n".format( def_desc, crit_desc, gem_name, actor_desc, self.get_class(), self.importer.url )
		
		# Passive Skill Tree
			
		line2 = "^(Level {:n}) ^[[Tree]]({:s})".format(self.level, self.passives_url)
		
		# pob.party link
		try:
			web_pob = pob_party.get_url(self.importer)
			line2 += " [^([Open in Browser])]({:s})".format(web_pob)
		except PoBPartyException as e:
			logging.warning("Failed to get pob party url for {}. {}".format(self.importer.key, e))
			pass
			
		# author
		line2 += " ^| ^by ^[{:s}](https://reddit.com/{})\n*****\n".format(self.author, self.author)
		
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
		
		if self.has_keystone("Chaos Inoculation"):
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
			
			if self.has_keystone("Mind Over Matter"):
				if self.is_fully_geared() and self.level > 1:
					# Display the full amount of unreserved mana
					if self.get_stat('ManaUnreserved') > 0:
						body += " | {:n} **Mana**".format(self.get_stat('ManaUnreserved'))
					
					if self.has_keystone("Eldritch Battery"):
						body += " | {:n} **ES**".format(self.get_stat('EnergyShield'))
					
					# Calculate the maximum amount of mana that contributes to the player's EHP
					mom_pct = self.get_MoM_percent()
					max_ehp_mana = self.get_stat('LifeUnreserved') * ( mom_pct / ( 1 - mom_pct ) )
					
					eff_max_mana = self.get_stat('ManaUnreserved')
					
					if self.has_keystone("Eldritch Battery"):
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
			if not (hasattr(self.main_gem.data, 'cast_time') and self.main_gem.data.cast_time == 0):
				if self.get_stat("Cooldown") > 0:
					pieces.append("{:.2f}s **CD**".format(self.get_stat("Cooldown")))
				else:
					pieces.append("{:.2f} **{}**".format(self.get_speed(), self.get_speed_str()))
		
		if self.main_gem.is_totem():
			pieces.append("{} **Totems**".format(self.main_gem.get_totem_limit()))
		
		if self.get_stat('CritChance') >= 20 and not self.has_keystone("Elemental Overload"):
			pieces.append("{:.2f}% **Crit**".format(self.get_stat('CritChance')))

			# Only show if crit multi is positive. Sometimes its not (perfect agony)
			# FIXME: Ideally, we show ailment multi instead, but that info isn't in the PoB export.
			if self.get_stat('CritMultiplier') > 1:
				pieces.append("{:n}% **Multi**".format(self.get_stat('CritMultiplier')*100))
			
		if self.main_gem.is_trap() and self.get_stat("TrapCooldown") > 0:
			pieces.append("{:.2f}s **Cooldown**".format(self.get_stat("TrapCooldown")))
		
		if len(pieces) > 0:
			line = " | ".join(pieces)
			body += '^' + line.replace(' ', ' ^')
		
		body += self.__get_config_string__()
		
		#logging.debug(body)
		return body
