import util

PlayerStats_to_parse = [
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
]

MinionStats_to_parse = [
	"TotalDPS",
]

class StatException(Exception):
	pass

def isCI(stats):
	return stats['Life'] == 1
	
def isLowLife(stats):
	return stats['LifeUnreservedPercent'] < 35

def isMoM(stats): #FIXME
	return stats['ManaUnreserved'] >= 1500

def isHybrid(stats):
	return not isCI(stats) and not isLowLife(stats) and stats['EnergyShield'] >= stats['Life'] * 0.25
	
def get_main_skill( build, root ):
	main_socket_group = int(build.attrib['mainSocketGroup'])
	skills = root.find('Skills')
	if len(skills) == 0:
		raise BotException('Build has no skills')
	return skills[main_socket_group-1]
	
def get_main_gem( build = False, root = False, skill = False ):
	if skill == False:
		skill = get_main_skill(build, root)
	
	for gem in skill.findall('Gem'):
		if not "Support" in gem.attrib['skillId']:
			return gem
	
def parse_stats_from_xml(root):
	build = root.find('Build')
	
	stats = {}
	mstats = {}
	
	for stat in build.findall('PlayerStat'):
		if stat.attrib['stat'] in PlayerStats_to_parse:
			stats[stat.attrib['stat']] = float(stat.attrib['value'])
			
	for stat in build.findall('MinionStat'):
		if stat.attrib['stat'] in MinionStats_to_parse:
			mstats[stat.attrib['stat']] = float(stat.attrib['value'])
			
	for stat in PlayerStats_to_parse:
		if stat not in stats:
			stats[stat] = 0
			
	for stat in MinionStats_to_parse:
		if stat not in mstats:
			mstats[stat] = 0
	
	return (stats,mstats)

def get_header(root, stats, bin_url, author):
	build = root.find('Build')
	
	# Defense descriptor
	def_desc = ""
	if isCI(stats):
		def_desc = "CI"
	elif isMoM(stats):
		def_desc = "MoM"
	elif isLowLife(stats):
		def_desc = "LL"
		
	if isHybrid(stats):
		if def_desc != "":
			def_desc = " " + def_desc
		def_desc = "Hybrid" + def_desc
		
	#if def_desc == "":
	#	def_desc = "Life"
	
	# Crit descriptor
	crit_desc = ""
	if stats["CritChance"] >= 20:
		crit_desc = " Crit"
		
	skill = get_main_skill( build, root )
	
	# Skill Descriptor
	gem = get_main_gem( skill = skill )
	#print gem
	gem_name = gem.attrib['nameSpec']
	#print gem_name
	
	# Totem/Trap/Mine Descriptor
	actor_desc = ''
	
	for gem in skill.findall('Gem'):
		if gem.attrib['skillId'] == "SupportSpellTotem" or gem.attrib['skillId'] == "SupportRangedAttackTotem":
			actor_desc = " Totem"
			break
		elif gem.attrib['skillId'] == "SupportRemoteMine":
			actor_desc = " Mine"
			break
		elif gem.attrib['skillId'] == "SupportTrap":
			actor_desc = " Trap"
			break
	
	# Ascendancy descriptor
	class_desc = build.attrib['className']
	if build.attrib['ascendClassName'] != "None":
		class_desc = build.attrib['ascendClassName']
	
	header = "###[" + def_desc + crit_desc + " " + gem_name + actor_desc + " " + class_desc + "](" + bin_url + ")\n"
	
	# Passive Skill Tree
	tree = root.find('Tree')
	active_spec = tree.findall('Spec')[int(tree.attrib['activeSpec'])-1]
	tree_url = active_spec.find('URL').text.strip()
	
	line2 = "Level {:s} [(Tree)]({:s}) | by /u/{:s}\n*****\n".format(build.attrib['level'], tree_url, author.name)
	header += '^' + line2.replace(' ', ' ^')
	
	#print header
	return header
	
def get_body(root, stats, mstats):
	body = ""
	build = root.find('Build')
	
	# First line (EHP stuff)
	
	total_ehp = 0;
	show_ehp = False
	
	if isCI(stats):
		body = "{:n} **ES**".format(stats['EnergyShield'])
		total_ehp += stats['EnergyShield']
	else:
		body = "{:n} **Life**".format(stats['Life'])
		total_ehp += stats['Life']
		
		if isMoM(stats):
			body += " | {:n} **Mana**".format(stats['ManaUnreserved'])
			total_ehp += stats['ManaUnreserved']
			show_ehp = True
			
		if isHybrid(stats):
			body += " | {:n} **ES**".format(stats['EnergyShield'])
			total_ehp += stats['EnergyShield']
			show_ehp = True
	
	if show_ehp:
		body += " | {:n} **total** **EHP**".format(total_ehp)
	
	body = '^' + body.replace(' ', ' ^') + "\n"
	
	# Second line (defenses)
	
	line = ""
	
	if stats['MeleeEvadeChance'] >= 15:
		line += "{:.0f}% **Evade**".format(stats['MeleeEvadeChance'])
	
	if stats['PhysicalDamageReduction'] >= 10:
		if line != "":
			line += " | "
		line += "{:n}% **Phys** **Mitg**".format(stats['PhysicalDamageReduction'])
	
	if stats['BlockChance'] >= 30:
		if line != "":
			line += " | "
		line += "{:n}% **Block**".format(stats['BlockChance'])
	
	if stats['SpellBlockChance'] > 0:
		if line != "":
			line += " | "
		line += "{:.0f}% **Spell** **Block**".format(stats['SpellBlockChance'])
	
	if stats['AttackDodgeChance'] > 3:
		if line != "":
			line += " | "
		line += "{:n}% **Dodge**".format(stats['AttackDodgeChance'])
	
	if stats['SpellDodgeChance'] > 3:
		if line != "":
			line += " | "
		line += "{:n}% **Spell** **Dodge**".format(stats['SpellDodgeChance'])
	
	if line != "":
		line = '^' + line.replace(' ', ' ^') + '\n'
		body += line
	
	body += "\n"
	
	## Offense
	
	skill = get_main_skill(build, root)
	gem = get_main_gem( skill = skill )
	gem_name = gem.attrib['nameSpec']
	links = 0
	
	for g in skill.findall('Gem'):
		if g.attrib['enabled'] == "true" and (gem == g or "Support" in g.attrib['skillId']):
			links += 1

	dps = max(stats['TotalDPS'], stats['TotalDot'] + stats['DecayDPS'])
	mdps = mstats['TotalDPS'] * stats['ActiveMinionLimit']
	
	if dps <= 0 and mdps <= 0:
		raise StatException('Active skill does no DPS!')
	
	dps_str = ""
	if mdps > dps:
		dps = mstats['TotalDPS']
		dps_str = "{:s} DPS per minion | {:s} total DPS".format(util.floatToSigFig(mstats['TotalDPS']), util.floatToSigFig(mstats['TotalDPS'] * stats['ActiveMinionLimit']))
	else:
		dps_str = "{:s} DPS".format(util.floatToSigFig(dps))
		
	body += "**{:s}** *({:n}L)* - *{:s}*".format(gem_name, links, dps_str) + '  \n'
	
	line = "{:.2f} **Use/sec**".format(stats['Speed'])
	
	if stats['CritChance'] >= 20:
		line += " | {:.2f}% **Crit** | {:n}% **Multi**".format(stats['CritChance'], stats['CritMultiplier']*100)
		
	body += '^' + line.replace(' ', ' ^') + '\n'
	
	#print body
	return body + "\n*****\n"
	
def get_footer():
	footer = "[^Path of Building](https://github.com/Openarl/PathOfBuilding) | This reply will be automatically removed if its parent comment is deleted. | [Feedback?](https://www.reddit.com/r/PoBPreviewBot/)"
	footer = footer.replace(' ', ' ^')
	return footer
	
def get_response_from_xml(bin_url, root, author):
	parsed = parse_stats_from_xml(root)
	stats = parsed[0]
	mstats = parsed[1]
	
	response = get_header(root, stats, bin_url, author)
	response += get_body(root, stats, mstats)
	response += get_footer()
	
	response = response.replace('\n', '  \n')
	
	return response