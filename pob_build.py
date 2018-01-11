import util
import base64
import re
import passive_skill_tree as passives
from name_overrides import skill_overrides
from name_overrides import build_defining_uniques
from gem_data import support_gems as support_gem_data
import praw.models

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
		],
	},
	{
		'elementType': 'MinionStat',
		'key': 'minion',
		'stats': [
			"TotalDPS",
			"WithPoisonDPS",
		],
	},
]

class StatException(Exception):
	pass
	
class UnsupportedException(Exception):
	pass
	
class socket_group_t:
	def __init__(self, skill_xml, build):
		self.xml = skill_xml
		self.build = build
		
		self.__get_parent_item__()
		self.__create_gems__()
		
	def __create_gems__(self):
		self.gems = []
		
		for gem_xml in self.xml.findall('Gem'):
			self.gems.append(gem_t(gem_xml, self))
			
	def __get_parent_item__(self):
		if 'slot' in self.xml.attrib:
			slot = self.xml.attrib['slot']
			self.item = self.build.equipped_items[slot]
		else:
			self.item = None
		
	def getNthActiveGem(self, n):
		currentSkill = 1
		for gem in self.gems:
			if not "Support" in gem.id and gem.enabled:
				if currentSkill == n:
					return gem
				else:
					currentSkill += 1
					
		if currentSkill > 1:
			raise Exception('mainActiveSkill exceeds total number of active skill gems in socket group.')
		else:
			raise Exception('mainSocketGroup has no active skill gem!')
	
class gem_t:
	def __init__(self, gem_xml, socket_group):
		self.xml = gem_xml
		
		self.build = socket_group.build
		self.socket_group = socket_group
		self.item = socket_group.item
		
		self.__parse_name__()
		
		self.enabled = self.xml.attrib['enabled'].lower() == "true"
		self.id = self.xml.attrib['skillId']
		self.level = int(self.xml.attrib['level'])
		self.quality = int(self.xml.attrib['quality'])
		
		self.data = self.__get_gem_data__(self.name)
		
	def __parse_name__(self):
		name = self.xml.attrib['nameSpec']
		
		if name in skill_overrides:
			self.name = skill_overrides[name]
		else:
			self.name = name
			
	def __get_gem_data__(self, name):
		name = name.lower()
		
		if name in support_gem_data:
			return support_gem_data[name]
		
	def is_supported_by(self, support):
		support = support.lower()
		
		for gem in self.socket_group.gems:
			if gem.enabled and support == self.name.lower():
				return True
		
		if self.item is not None:
			return self.item.grants_support_gem(support)
			
		return False
	
	def get_support_gem_str(self):
		str = ""

		# Support gems from xml (socketed into the item)
		for gem in self.socket_group.gems:
			if gem.enabled and "Support" in gem.id:
				str += "[{:s}]({:s}#support-gem-{:s})".format(gem.data.shortcode, gem.data.wiki_url, gem.data.color_str)
				
		# Support gems granted by the item
		if self.item is not None:
			for support in self.item.support_mods:
				data = self.__get_gem_data__(support)
				
				if data:
					str += "[{:s}]({:s}#support-gem-{:s})".format(data.shortcode, data.wiki_url, data.color_str)
				else:
					print("Warning: Support gem '{}' was not found in gem data and was ommitted in gem str!".format(support));
				
		return str
	
class item_t:
	def __init__(self, item_xml):
		self.xml = item_xml
		self.id = int(self.xml.attrib['id'])
		
		self.__parse_xml__()
		
	def __parse_xml__(self):
		rows = self.xml.text.split('\n')
		
		#print repr(rows)
		
		reg = re.compile("Rarity: ([A-Z])+")
		s = reg.search(rows[1])
		
		if not s:
			raise StatException('Failure to parse rarity of Item id={:.0f}'.format(self.id))
			
		self.rarity = s.group(1)
		
		self.name = rows[2].strip()
		self.base = rows[3].strip()
		
		self.__parse_for_support_gems__(rows)
		
	def __parse_for_support_gems__(self, rows):
		# Match in lower case just in case
		reg = re.compile("socketed gems are supported by level \d+ (.+)")
		
		self.support_mods = []
	
		for r in rows:
			s = reg.search(r.lower())
			if s:
				self.support_mods.append(s.group(1).strip())
	
	def grants_support_gem(self, support):
		return support.lower() in self.support_mods

class build_t:
	config_bools = {
		"conditionFullLife": "Full Life",
		"conditionKilledRecently": "Killed Recently",
		#"conditionOnConsecratedGround": "Cons. Ground",
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
	}
	
	config_numbers = {
		"enemyFireResist": "{:+n}% Fire Res",
		"enemyColdResist": "{:+n}% Cold Res",
		"enemyLightningResist": "{:+n}% Light Res",
		"enemyChaosResist": "{:+n}% Chaos Res",
		"enemyPhysicalReduction": "{:+n}% Phys Reduction",
		"multiplierPoisonOnEnemy": "Poison \({:n}\)",
	}
	
	# Dict of Wither Stacks by its corresponding skillPart
	wither_stacks = {
		"1": 1,
		"2": 5, 
		"3": 10,
		"4": 20,
	}
	
	def __init__(self, xml, pastebin_url, author):
		self.xml = xml
		self.xml_build = self.xml.find('Build')
		self.xml_config = self.xml.find('Config')
		self.pastebin = pastebin_url
		
		self.__parse_items__()
		self.__parse_author__(author)
		self.__parse_stats__()
		self.__parse_passive_skills__()
		self.__parse_character_info__()
		
		self.__check_build_eligibility__()
		
	def __parse_author__(self, author):
		if isinstance(author, praw.models.reddit.redditor.Redditor):
			self.author = "/u/{:s}".format(author.name)
		elif isinstance(author, str) or isinstance(author, unicode):
			self.author = author
		else:
			raise Exception('Build has invalid author')
		
	def __parse_character_info__(self):
		self.class_name = self.xml_build.attrib['className']
		
		if self.xml_build.attrib['ascendClassName'] != "None":
			self.ascendancy_name = self.xml_build.attrib['ascendClassName']
			
		self.level = self.xml_build.attrib['level']
		
		self.__parse_main_socket_group__()
		self.__parse_main_gem__()
		
	def __parse_main_socket_group__(self):
		main_socket_group = int(self.xml_build.attrib['mainSocketGroup'])
		skills = self.xml.find('Skills')
		if len(skills) == 0:
			raise StatException('Build has no skills')
		self.main_socket_group = socket_group_t(skills[main_socket_group-1], self)
		
		# check to make sure main socket group is not in an inactive weapon set
		if 'slot' in self.main_socket_group.xml.attrib and "Weapon" in self.main_socket_group.xml.attrib['slot']:
			useSecondWeaponSet = self.xml.find('Items').attrib['useSecondWeaponSet'].lower() == "true"
			slot = self.main_socket_group.xml.attrib['slot']
			
			if ( not useSecondWeaponSet and "Swap" in slot ) or ( useSecondWeaponSet and "Swap" not in slot ):
				raise StatException('mainSocketGroup is in inactive weapon set.')
		
	def __parse_main_gem__(self):
		if self.main_socket_group is None:
			self.__parse_main_socket_group__()
			
		nthSkill = int(self.main_socket_group.xml.attrib['mainActiveSkill'])
		self.main_gem = self.main_socket_group.getNthActiveGem(nthSkill)
		
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
			raise StatException('invalid passive skill tree')
		
		ver = ord(b[0]) * 16777216 + ord(b[1]) * 65536 + ord(b[2]) * 256 + ord(b[3])
		
		if ver > 4:
			raise StatException("Invalid tree link (unknown version number '{:s}')".format(ver))
			
		#nodes = b.replace(ver >= 4 and chr(8) or chr(7), chr(-1))
		nodes = b
		#print nodes
		
		self.passives_by_name = {}
		self.passives_by_id = {}
		
		for i in range(8, len(nodes)-1, 2):
			id = ord(nodes[i-1]) * 256 + ord(nodes[i])
			
			if id in passives.nodes:
				self.passives_by_name[passives.nodes[id]['dn']] = id
				self.passives_by_id[id] = True
			
		#print allocNodes
		
	def __parse_items__(self):
		self.items = {}
		
		xml_items = self.xml.find('Items')
		
		for i in xml_items.findall('Item'):
			self.items[int(i.attrib['id'])] = item_t(i)
			
		self.equipped_items = {}
			
		for slot in xml_items.findall('Slot'):
			self.equipped_items[slot.attrib['name']] = self.items[int(slot.attrib['itemId'])]
			
		#print repr(self.equipped_items)
		
	def __check_build_eligibility__(self):
		if self.main_gem.is_supported_by("Cast on Critical Strike") or self.has_item_equipped("Cospri's Malice"):
			raise UnsupportedException('Cast on Critical Strike builds are not supported.')
		
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
			raise StatException()
			
	def has_item_equipped(self, name):
		for i in self.equipped_items:
			if self.equipped_items[i].name.lower() == name.lower():
				# check to make sure main socket group is not in an inactive weapon set
				if "Weapon" in i:
					useSecondWeaponSet = self.xml.find('Items').attrib['useSecondWeaponSet'].lower() == "true"
					
					if ( useSecondWeaponSet and "Swap" in i ) or ( not useSecondWeaponSet and "Swap" not in i ):
						return True
				else:
					return True
				
		return False
		
	def is_low_life(self):
		return self.stats['player']['LifeUnreservedPercent'] < 35

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
		return not self.has_passive_skill("Chaos Inoculation") and not self.is_low_life() and self.stats['player']['EnergyShield'] >= self.stats['player']['LifeUnreserved'] * 0.25
		
	def get_main_descriptor(self):
		for unique in build_defining_uniques:
			if self.has_item_equipped(unique):
				if isinstance(build_defining_uniques[unique], str):
					return build_defining_uniques[unique]
				else:
					return unique
		
		return self.main_gem.name
		
	def get_bleed_dps(self):
		bleed = self.stats['player']['BleedDPS']
		
		if self.has_passive_skill("Crimson Dance"):
			desc = "\n".join(passives.nodes[self.passives_by_name["Crimson Dance"]]['sd'])
			max_stacks = re.search("You can inflict Bleeding on an Enemy up to (\d+) times", desc).group(1)
			bleed *= int(max_stacks)
			
		return bleed
		
	def get_poison_dps(self):
		return self.stats['player']['WithPoisonDPS'] - self.stats['player']['TotalDPS'] - self.stats['player']['TotalDot']
		
	def get_dps_breakdown(self):
		if self.stats['minion']['TotalDPS'] > 0:
			if self.stats['player']['ActiveMinionLimit'] > 1:
				return [
					(self.stats['minion']['TotalDPS'] * self.stats['player']['ActiveMinionLimit'], "total DPS"),
					(self.stats['minion']['TotalDPS'], "DPS per minion"),
				]
			else:
				return [ (self.stats['minion']['TotalDPS'], "DPS") ]
		else:
			dot = 0
			direct = 0
			
			# If the base DoT DPS is greater than the direct + poison DPS, conclude this skill is only used to maintain the DoT.
			if self.stats['player']['TotalDot'] > 0.5 * self.stats['player']['WithPoisonDPS']:
				# Base DoT (doesn't include decay and other shit unlike what the attribute name would imply)
				dot += self.stats['player']['TotalDot']
				#print "{:.2f} base DoT".format(self.stats['player']['TotalDot'])
			else:
				# Direct DPS
				direct += self.stats['player']['TotalDPS']
				#print "{:.2f} direct".format(self.stats['player']['TotalDPS'])
			
				if self.stats['player']['WithPoisonDPS'] > 0:
					# Poison
					dot += self.get_poison_dps()
					#print "{:.2f} poison".format(self.stats['player']['WithPoisonDPS'] - self.stats['player']['TotalDPS'])
					
				# base DoT still contributes to DPS total (if relevant)
				if self.stats['player']['TotalDot'] > 0:
					# Base DoT
					dot += self.stats['player']['TotalDot']
			
			# Bleed
			dot += self.get_bleed_dps()
			#print "{:.2f} bleed".format(self.get_bleed_dps())
			
			# Ignite
			dot += self.stats['player']['IgniteDPS']
			#print "{:.2f} ignite".format(self.stats['player']['IgniteDPS'])
			
			# Decay
			dot += self.stats['player']['DecayDPS']
			#print "{:.2f} decay".format(self.stats['player']['DecayDPS'])
			
			total = direct + dot
			
			# if direct DPS is >95% of the total DPS
			if max(direct, self.stats['player']['TotalDot']) >= 0.95 * total:
				return [ ( total, "DPS" ) ]
			else:
				r = [ ( total, "total DPS" ) ]
				
				# Base DoT
				if self.stats['player']['TotalDot'] > 0.01 * total:
					r.append( ( self.stats['player']['TotalDot'], "skill DoT DPS" ) )
				
				# Bleed
				if self.get_bleed_dps() > 0.01 * total:
					r.append( ( self.get_bleed_dps(), "bleed DPS" ) )
					
				# Ignite
				if self.stats['player']['IgniteDPS'] > 0.01 * total:
					r.append( ( self.stats['player']['IgniteDPS'], "ignite DPS" ) )
				
				# Poison
				if self.get_poison_dps() > 0.01 * total:
					r.append( ( self.get_poison_dps(), "poison DPS" ) )
					
				# Decay
				if self.stats['player']['DecayDPS'] > 0.01 * total:
					r.append( ( self.stats['player']['DecayDPS'], "decay DPS" ) )
		
				return r
				
	def get_enabled_gem(self, gem_name):
		for gem in self.xml.findall("./Skills/Skill/Gem[@nameSpec='{}']".format(gem_name)):
			if "enabled" in gem.attrib and gem.attrib['enabled'].lower() == "true":
				return gem
				
		return None
		
	def __get_config_value__(self, name):
		xml_input = self.xml_config.find("*[@name='{:s}']".format(name))
		
		if xml_input is None:
			#print "{:s}: {:s}".format(name, None)
			return None
			
		if 'boolean' in xml_input.attrib:
			#print "{:s}: {:s}".format(name, xml_input.attrib['boolean'].lower())
			return xml_input.attrib['boolean'].lower()
			
		if 'number' in xml_input.attrib:
			#print "{:s}: {:n}".format(name, float(xml_input.attrib['number']))
			return float(xml_input.attrib['number'])
			
		if 'string' in xml_input.attrib:
			#print "{:s}: {:s}".format(name, xml_input.attrib['string'].lower())
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
				dps_config.append(self.config_numbers[opt_name].format(self.__get_config_value__(opt_name)))
				
		if self.get_enabled_gem("Vaal Haste") is not None:
			dps_config.append("Vaal Haste")
				
		wither = self.get_enabled_gem("Wither")
		if wither is not None:
			dps_config.append("Wither \({}\)".format(self.wither_stacks[wither.attrib['skillPart']]))
				
		return dps_config
			
	def __get_config_string__(self):
		dps_config = self.__get_config_array__()
		
		if len(dps_config) == 0:
			return ""
		
		return "  \n\n" + " **Config:** {:s}".format(", ".join(dps_config)).replace(' ', " ^^")
			
		
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
		if self.stats['player']["CritChance"] >= 20:
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
		
		header = "###[{:s}{:s} {:s}{:s} {:s}]({:s})\n".format( def_desc, crit_desc, gem_name, actor_desc, self.get_class(), self.pastebin )
		
		# Passive Skill Tree
		
		line2 = "Level {:s} [(Tree)]({:s}) | by {:s}\n*****\n".format(self.level, self.passives_url, self.author)
		line2 = '^' + line2.replace(' ', ' ^')
		
		if hasattr(self, 'ascendancy_name'):
			line2 = "[](#{:s}) ".format(self.ascendancy_name.lower()) + line2
			
		header += line2
		
		#print header
		return header
	
	def get_response_body(self):
		body = ""
		
		# First line (EHP stuff)
		
		total_ehp = 0;
		show_ehp = False
		
		if self.has_passive_skill("Chaos Inoculation"):
			body = "{:n} **ES**".format(self.stats['player']['EnergyShield'])
			total_ehp += self.stats['player']['EnergyShield']
		else:
			body = "{:n} **Life**".format(self.stats['player']['LifeUnreserved'])
			total_ehp += self.stats['player']['LifeUnreserved']
			
			if self.is_MoM():
				# Display the full amount of unreserved mana
				body += " | {:n} **Mana**".format(self.stats['player']['ManaUnreserved'])
				
				# Calculate the maximum amount of mana that contributes to the player's EHP
				mom_pct = self.get_MoM_percent()
				max_ehp_mana = self.stats['player']['LifeUnreserved'] * ( mom_pct / ( 1 - mom_pct ) )
				# Add up to the max amount
				total_ehp += int( min( self.stats['player']['ManaUnreserved'], max_ehp_mana ) )
				
				show_ehp = True
				
			if self.is_hybrid() or self.is_low_life():
				body += " | {:n} **ES**".format(self.stats['player']['EnergyShield'])
				total_ehp += self.stats['player']['EnergyShield']
				show_ehp = True
		
		if show_ehp:
			body += " | {:n} **total** **EHP**".format(total_ehp)
		
		body = '^' + body.replace(' ', ' ^') + "\n"
		
		# Second line (defenses)
		
		line = ""
		
		if self.stats['player']['MeleeEvadeChance'] >= 15:
			line += "{:.0f}% **Evade**".format(self.stats['player']['MeleeEvadeChance'])
		
		if self.stats['player']['PhysicalDamageReduction'] >= 10:
			if line != "":
				line += " | "
			line += "{:n}% **Phys** **Mitg**".format(self.stats['player']['PhysicalDamageReduction'])
		
		if self.stats['player']['BlockChance'] >= 30:
			if line != "":
				line += " | "
			line += "{:n}% **Block**".format(self.stats['player']['BlockChance'])
		
		if self.stats['player']['SpellBlockChance'] > 0:
			if line != "":
				line += " | "
			line += "{:.0f}% **Spell** **Block**".format(self.stats['player']['SpellBlockChance'])
		
		if self.stats['player']['AttackDodgeChance'] > 3:
			if line != "":
				line += " | "
			line += "{:n}% **Dodge**".format(self.stats['player']['AttackDodgeChance'])
		
		if self.stats['player']['SpellDodgeChance'] > 3:
			if line != "":
				line += " | "
			line += "{:n}% **Spell** **Dodge**".format(self.stats['player']['SpellDodgeChance'])
		
		if line != "":
			line = '^' + line.replace(' ', ' ^') + '\n'
			body += line
		
		body += "\n"
		
		## Offense
		gem_name = self.main_gem.name
		links = 0
		
		for gem in self.main_socket_group.gems:
			if gem.enabled and (self.main_gem.xml == gem.xml or "Support" in gem.id):
				links += 1
				
		if links < 4:
			raise StatException('{:s} is in less than a 4L ({:.0f}L).'.format(  self.main_gem.name, links ) )

		dps_breakdown = self.get_dps_breakdown()
		
		if dps_breakdown[0][0] <= 0:
			raise StatException('Active skill \'{:s}\' does no DPS! {:s}'.format( self.main_gem.name, repr(dps_breakdown) ))
		elif dps_breakdown[0][0] < 500:
			raise StatException('Active skill \'{:s}\' does negligible DPS! {:s}'.format( self.main_gem.name, repr(dps_breakdown) ))
		
		dps_str = ""
		
		for b in dps_breakdown:
			if dps_str != "":
				dps_str += " | "
				
			dps_str += "{:s} {:s}".format(util.floatToSigFig(b[0]), b[1])
			
		body += "**{:s}** {:s} *({:n}L)* - *{:s}*".format(gem_name, self.main_gem.get_support_gem_str(), links, dps_str) + '  \n'
		
		line = "{:.2f} **Use/sec**".format(self.stats['player']['Speed'])
		
		if self.stats['player']['CritChance'] >= 20:
			line += " | {:.2f}% **Crit** | {:n}% **Multi**".format(self.stats['player']['CritChance'], self.stats['player']['CritMultiplier']*100)
			
		body += '^' + line.replace(' ', ' ^')
		
		body += self.__get_config_string__()
		
		#print body
		return body