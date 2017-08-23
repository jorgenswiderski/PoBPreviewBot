import util

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

class pob_build:
	stats = {}
	
	def __init__(self, xml, pastebin_url, author):
		self.xml = xml
		self.build = self.xml.find('Build')
		self.pastebin = pastebin_url
		self.author = author
		
		self.__parse_stats__()
		self.__parse_passive_skills__()
		self.__parse_character_info__()
		
	def __parse_character_info__(self):
		self.class_name = self.build.attrib['className']
		
		if self.build.attrib['ascendClassName'] != "None":
			self.ascendancy_name = self.build.attrib['ascendClassName']
			
		self.level = self.build.attrib['level']
		
		self.__parse_main_skill__()
		self.__parse_main_gem__()
		
	def __parse_main_skill__(self):
		main_socket_group = int(self.build.attrib['mainSocketGroup'])
		skills = self.xml.find('Skills')
		if len(skills) == 0:
			raise StatException('Build has no skills')
		self.main_skill = skills[main_socket_group-1]
		
	def __parse_main_gem__(self):
		if self.main_skill is None:
			self.__parse_main_skill__()
		
		for gem in self.main_skill.findall('Gem'):
			if not "Support" in gem.attrib['skillId']:
				self.main_gem = gem
				return
				
		raise StatException('mainSocketGroup has no active skill gem!')
		
	def __parse_stats__(self):
		for entry in stats_to_parse:
			key = entry['key']
			elementType = entry['elementType']
			self.stats[key] = {}
			
			for stat in self.build.findall(elementType):
				if stat.attrib['stat'] in entry['stats']:
					self.stats[key][stat.attrib['stat']] = float(stat.attrib['value'])
					
			for stat in entry['stats']:
				if stat not in self.stats[key]:
					self.stats[key][stat] = 0
					
	def __parse_passive_skills__(self):
		tree = self.xml.find('Tree')
		active_spec = tree.findall('Spec')[int(tree.attrib['activeSpec'])-1]
		self.passives_url = active_spec.find('URL').text.strip()
		
	def get_class(self):
		if self.ascendancy_name is not None:
			return self.ascendancy_name
			
		return self.class_name
					
	def isCI(self):
		return self.stats['player']['Life'] == 1
		
	def isLowLife(self):
		return self.stats['player']['LifeUnreservedPercent'] < 35

	def isMoM(self): #FIXME
		return self.stats['player']['ManaUnreserved'] >= 1500

	def isHybrid(self):
		return not self.isCI() and not self.isLowLife() and self.stats['player']['EnergyShield'] >= self.stats['player']['LifeUnreserved'] * 0.25
		
	def get_response(self):
		response = self.get_response_header()
		response += self.get_response_body()
		response += self.get_response_footer()
		
		return response.replace('\n', '  \n')
		
	def get_response_header(self):
		# Defense descriptor
		def_desc = ""
		if self.isCI():
			def_desc = "CI"
		elif self.isMoM():
			def_desc = "MoM"
		elif self.isLowLife():
			def_desc = "LL"
			
		if self.isHybrid():
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
		gem_name = self.main_gem.attrib['nameSpec']
		
		# Totem/Trap/Mine Descriptor
		actor_desc = ''
		
		for gem in self.main_skill.findall('Gem'):
			if gem.attrib['skillId'] == "SupportSpellTotem" or gem.attrib['skillId'] == "SupportRangedAttackTotem":
				actor_desc = " Totem"
				break
			elif gem.attrib['skillId'] == "SupportRemoteMine":
				actor_desc = " Mine"
				break
			elif gem.attrib['skillId'] == "SupportTrap":
				actor_desc = " Trap"
				break
		
		header = "###[{:s}{:s} {:s}{:s} {:s}]({:s})\n".format( def_desc, crit_desc, gem_name, actor_desc, self.get_class(), self.pastebin )
		
		# Passive Skill Tree
		
		line2 = "Level {:s} [(Tree)]({:s}) | by /u/{:s}\n*****\n".format(self.level, self.passives_url, self.author.name)
		header += '^' + line2.replace(' ', ' ^')
		
		#print header
		return header
	
	def get_response_body(self):
		body = ""
		
		# First line (EHP stuff)
		
		total_ehp = 0;
		show_ehp = False
		
		if self.isCI():
			body = "{:n} **ES**".format(self.stats['player']['EnergyShield'])
			total_ehp += self.stats['player']['EnergyShield']
		else:
			body = "{:n} **Life**".format(self.stats['player']['LifeUnreserved'])
			total_ehp += self.stats['player']['LifeUnreserved']
			
			if self.isMoM():
				body += " | {:n} **Mana**".format(self.stats['player']['ManaUnreserved'])
				total_ehp += self.stats['player']['ManaUnreserved']
				show_ehp = True
				
			if self.isHybrid():
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
		gem_name = self.main_gem.attrib['nameSpec']
		links = 0
		
		for g in self.main_skill.findall('Gem'):
			if g.attrib['enabled'] == "true" and (self.main_gem == g or "Support" in g.attrib['skillId']):
				links += 1

		dps = max(self.stats['player']['TotalDPS'], self.stats['player']['WithPoisonDPS'], self.stats['player']['TotalDot'] + self.stats['player']['DecayDPS'])
		mdps = self.stats['minion']['TotalDPS'] * self.stats['player']['ActiveMinionLimit']
		
		if dps <= 0 and mdps <= 0:
			raise StatException('Active skill does no DPS!')
		
		dps_str = ""
		if mdps > dps:
			dps = max(self.stats['minion']['TotalDPS'], self.stats['minion']['WithPoisonDPS'])
			dps_str = "{:s} DPS per minion | {:s} total DPS".format(util.floatToSigFig(dps), util.floatToSigFig(dps * self.stats['player']['ActiveMinionLimit']))
		else:
			dps_str = "{:s} DPS".format(util.floatToSigFig(dps))
			
		body += "**{:s}** *({:n}L)* - *{:s}*".format(gem_name, links, dps_str) + '  \n'
		
		line = "{:.2f} **Use/sec**".format(self.stats['player']['Speed'])
		
		if self.stats['player']['CritChance'] >= 20:
			line += " | {:.2f}% **Crit** | {:n}% **Multi**".format(self.stats['player']['CritChance'], self.stats['player']['CritMultiplier']*100)
			
		body += '^' + line.replace(' ', ' ^') + '\n'
		
		#print body
		return body + "\n*****\n"
		
	def get_response_footer(self):
		footer = "[^Path of Building](https://github.com/Openarl/PathOfBuilding) | This reply will be automatically removed if its parent comment is deleted. | [Feedback?](https://www.reddit.com/r/PoBPreviewBot/)" 
		return footer.replace(' ', ' ^')