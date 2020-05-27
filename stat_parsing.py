# Python
import re
import logging
import json
import time
import sre_constants
import glob

# 3rd Party

# Self
import logger
import passive_skill_tree
import util
from trie import Trie

'''
This will ONLY parse mods whose stat translations are present in the following files:
 - RePoE/stat_translations.json
 - RePoE/stat_translations/passive_skill.json

To add additional files, just drop them in the stat translations folder.

See here for more info:
https://github.com/brather1ng/RePoE/blob/master/docs/stat_translations.md
'''

def init_support_gem_stat_map(support_gem_ids):
	global support_gem_map

	support_gem_map = {}

	with open('data/mods.json', 'r') as f:
		mod_data = json.load(f)

	for mod_id, mod_dict in list(mod_data.items()):
		for stat in mod_dict['stats']:
			if stat['id'] in support_gem_ids:

				key = stat['id']
				values = []

				for effect in mod_dict['grants_effects']:
					values.append(effect['granted_effect_id'])

				support_gem_map[key] = values
				logging.log(logger.DEBUG_ALL, "Support gem stat {} mapped to {}".format(key, values))

				support_gem_ids.remove(key)

def init_keystone_stat_map(keystone_ids):
	global keystone_map

	keystone_map = {}

	for group in trans_data:
		for stat_id in group['ids']:
			if stat_id in keystone_ids:
				key = group['English'][0]['string']

				if key not in keystone_map:
					keystone_map[key] = []

				keystone_map[key].append(stat_id)
				logging.log(logger.DEBUG_ALL, "Keystone stat '{}' mapped to {}".format(stat_id, key))
				keystone_ids.remove(stat_id)

	logging.log(logger.DEBUG_ALL, keystone_map)

	assert len(keystone_ids) == 0

def is_whitelisted(group):
	common_elements = whitelist.intersection(set(group['ids']))

	return len(common_elements) > 0

def create_whitelist(data):
	global whitelist

	with open('stat_whitelist.json', 'r') as f:
		whitelist = set(json.load(f))

	# whitelist all support gem stats
	re_support = re.compile("Socketed Gems are Supported by Level", flags=re.IGNORECASE)
	support_gem_ids = set()

	for translation_group in data:
		variations = translation_group['English']

		matched = False

		for variation in variations:
			if re_support.search(variation['string']):
				matched = True
				break

		if matched:
			for id in translation_group['ids']:
				support_gem_ids.add(id)
				logging.debug("Whitelisted stat '{}'".format(id))

	whitelist.update(support_gem_ids)
	init_support_gem_stat_map(support_gem_ids)

	# whitelist all keystone stats
	re_keystone = re.compile("keystone_.+", flags=re.IGNORECASE)
	keystone_ids = set()

	for translation_group in data:
		for id in translation_group['ids']:
			if re_keystone.match(id):
				keystone_ids.add(id)
				logging.debug("Whitelisted stat '{}'".format(id))

	whitelist.update(keystone_ids)
	init_keystone_stat_map(keystone_ids)

	# whitelist cluster jewel enchantments
	re_cluster_ench = re.compile("Added Small Passive Skills grant", flags=re.IGNORECASE)

	cluster_ench_ids = set()

	for translation_group in data:
		variations = translation_group['English']

		matched = False

		for variation in variations:
			if re_cluster_ench.search(variation['string']):
				matched = True
				break

		if matched:
			for id in translation_group['ids']:
				cluster_ench_ids.add(id)
				logging.debug("Whitelisted stat '{}'".format(id))

	whitelist.update(cluster_ench_ids)
	global cluster_enchant_stats
	cluster_enchant_stats = cluster_ench_ids

	# whitelist cluster passive stats
	# (any cluster jewel stat that grants a passive)
	with open('data/cluster_jewel_notables.json', 'r') as f:
		cluster_passive_stat_ids = [n['jewel_stat'] for n in json.load(f)]

	whitelist.update(cluster_passive_stat_ids)

	# whitelist cluster enchant stats
	with open('data/cluster_jewels.json', 'r') as f:
		cluster_data = json.load(f)

		cluster_enchant_stats_ids = set()

		for key, value in list(cluster_data.items()):
			for skill_data in value['passive_skills']:
				for stat_id in list(skill_data['stats'].keys()):
					cluster_enchant_stats_ids.add(stat_id)
					logging.debug("Whitelisted stat '{}'".format(stat_id))

	whitelist.update(cluster_enchant_stats_ids)

	logging.debug("Finished whitelist with {} entries.".format(len(whitelist)))

def init():
	global trans_data

	with open('data/stat_translations.json', 'r') as f:
		trans_data = json.load(f)

	for file in glob.glob('data/stat_translations/*.json'):
		with open(file, 'r') as f:
			trans_data += json.load(f)

	create_whitelist(trans_data)

	# apply stat whitelist
	trans_data = list(filter(is_whitelisted, trans_data))

	'''
	Construct a Trie regex out of all the translation strings
	This is a very very long, very very fast regex that will match any of the sub strings we feed it
	We will use this later to efficiently find areas of interest in item text

	Also construct a dict that will allow us to map the Trie search results
	back to any relevant specific stats that we should search for
	This will save us from having to perform every single regex on the item's mods
	'''
	global trie_stat_map
	trie_stat_map = {}
	trie = Trie()
	longest_substr = re.compile('[^(){}]+')

	for translation_group in trans_data:
		variations = translation_group['English']

		for variation in variations:
			# For each variation, find the longest plain-text string (ie doesn't contain any special elements)
			#tweaked = re.sub(r'{\d}', '{}', variation['string'])
			m = re.findall(longest_substr, variation['string'])
			m = sorted(m, key=lambda ss: len(ss))
			substr = m.pop(len(m)-1)

			trie.add(substr)

			key = substr.lower()

			# two stats could have the same plain text substr, so map the substr to a set of indices
			if key not in trie_stat_map:
				trie_stat_map[key] = set()

			trie_stat_map[key].add(trans_data.index(translation_group))
			#logging.info("Mapped '{}' to translation group #{}.".format(substr, trans_data.index(translation_group)))

	# make two regexes
	# the first just matches to any substr
	global trans_trie_regex
	trans_trie_regex = re.compile(trie.pattern(), re.IGNORECASE)
	# the second is a forward-looking capture that can be used to match ALL substrings (even if those substrings overlap)
	# this is used in conjustion with trie_stat_map to retrieve all relevant translation groups
	global trans_trie_regex_all
	trans_trie_regex_all = re.compile("(?=({}))".format(trie.pattern()), re.IGNORECASE)

	'''
	with open('whitelist_example.json', 'w') as f:
		json.dump(trans_data, f, sort_keys=True, indent=4)
	'''

	for translation_group in trans_data:
		ids = translation_group['ids']
		variations = translation_group['English']

		for variation in variations:
			variation['regex'] = make_regex(variation)
			#logging.info('Created regex for: "{}" ==>  "{}"'.format(variation['string'], variation['regex']))


def escape(s):
	if len(s) > 0 and s[0] == '+':
		s = '\\' + s

	s = re.sub('\?', '\?', s)

	return s

# returns a list of stats

def make_regex(variation):
	# base string
	vstr = escape(variation['string'])

	for i in range(0, len(variation['format'])):
		needle = "\{" + str(i) + "}"
		stat_format = variation['format'][i]

		if stat_format == "ignore":
			continue

		replacement = None

		if stat_format == "#":
			replacement = "(\\\\d+)"
		elif stat_format == "+#":
			replacement = "[+-](\\\\d+)"
		elif stat_format == "#%":
			replacement = "(\\\\d+)%"
		elif stat_format == "+#%":
			replacement = "[+-](\\\\d+)%"
		else:
			raise ValueError("unhandled format value")

		vstr = re.sub(needle, replacement, vstr)

	return vstr

class combined_stats_t:
	def __init__(self, trans_str, stats_dict=None, item=None, passive=None):
		if item is None and passive is None:
			raise ValueError("stat_t passed invalid args, must provide source item or passive")

		if trans_str is None and stats_dict is None:
			raise ValueError("stat_t passed invalid args, must provide stat strings or stat dict")

		self.item = item
		self.passive = passive
		self.stats = []
		self.dict_cache = {}
		self.cache_valid = True

		if trans_str is not None:
			self.parse_str(trans_str)
		else:
			for key, value in list(stats_dict.items()):
				self.add(stat_t(None, {key: value}))

	def add(self, stat):
		self.stats.append(stat)
		self.cache_valid = False

	def parse_str(self, trans_block, item=1, passive=None):
		global trans_data

		# pad with new lines so we can easily detect each mod
		trans_block = "\n{}\n".format(trans_block)

		# Use Trie Regex as an extremely quick first pass to see if there is anything of interest in the item's mods
		m = re.search(trans_trie_regex, trans_block)

		if not m:
			return

		# Find all trie matches so we know what specifically to parse
		matches = re.findall(trans_trie_regex_all, trans_block)

		trans_group_indices = set()

		for match in matches:
			trans_group_indices.update(trie_stat_map[match.lower()])

		#logging.info(trans_block)

		for tg_idx in trans_group_indices:
			translation_group = trans_data[tg_idx]
			ids = translation_group['ids']

			#logging.info(ids)

			if 'dummy_stat_display_nothing' in ids:
				continue

			variations = translation_group['English']

			for variation in variations:
				pattern = "\n{}\n".format(variation['regex'])

				try:
					match = re.search(pattern, trans_block, flags=re.IGNORECASE)
				except sre_constants.error as e:
					logging.error(pattern)
					raise e

				if match:
					if len(match.groups()) > 0:
						logging.log(logger.DEBUG_ALL, "Item text '{}' matches stat {} with values: {}".format(match.group(0).strip(), ids, match.groups()))
					else:
						logging.log(logger.DEBUG_ALL, "Item text '{}' matches stat {}".format(match.group(0).strip(), ids))

					# construct stat dict
					match_values = list(match.groups())
					stat_dict = {}

					for i in range(0, len(variation['format'])):
						stat_format = variation['format'][i]

						if stat_format == "ignore":
							stat_dict[ids[i]] = 1.0
						else:
							stat_dict[ids[i]] = float(match_values.pop(0))

							if len(variation['index_handlers']) > i and variation['index_handlers'][i] == 'negate':
								stat_dicts[ids[i]] *= -1

					stat = stat_t(match.group(0).strip(), stat_dict, item=item, passive=passive)
					self.add(stat)

					#logging.info(pattern)

					trans_block = re.sub(pattern.strip(), "", trans_block, flags=re.IGNORECASE)

					#logging.info(trans_block)

		for match in re.finditer("[^\n]+", trans_block):
			logging.log(logger.DEBUG_ALL, "Non-matched modifier: '{}'".format(match.group()))

	def build_cache(self):
		self.dict_cache = {}

		for stat in self.stats:
			for id, value in list(stat.dict.items()):
				if id not in self.dict_cache:
					self.dict_cache[id] = 0

				self.dict_cache[id] += value

		self.cache_valid = True

	def dict(self):
		if not self.cache_valid:
			self.build_cache()

		return self.dict_cache

class stat_t:
	def __init__(self, stat_str, stats, item=None, passive=None):
		if stat_str is not None:
			self._string = stat_str

		#self.dict = stats
		self.dict = stats
		self.item = item
		self.passive = passive

		logging.log(logger.DEBUG_ALL, self.dict)

	@property
	def string(self):
		try:
			return self._string
		except AttributeError:
			pass

		global trans_data

		stat_strs = []

		for stat_id, value in list(self.dict.items()):
			for translation_group in trans_data:
				translated = False

				if stat_id in translation_group['ids']:
					#logging.info("Found matching stat id '{}'".format(stat_id))

					# Loop through the variations
					for variation in translation_group['English']:
						# Find one that satifies the conditions
						if 'min' in variation['condition']:
							if value < variation['condition']['min']:
								continue

						if 'max' in variation['condition']:
							if value > variation['condition']['max']:
								continue

						formatted_value = None

						if len(variation['index_handlers']) > 0 and variation['index_handlers'][0] == "negate":
							value *= -1

						if variation['format'][0] == '#':
							formatted_value = "{}".format(value)
						elif variation['format'][0] == '+#':
							formatted_value = "{:+}".format(value)
						elif variation['format'][0] == '#%':
							formatted_value = "{}%".format(value)
						elif variation['format'][0] == '+#%':
							formatted_value = "{:+}%".format(value)
						elif variation['format'][0] == 'ignored':
							raise ValueError("Attempted to format stat '{}' with value '{}' but format is ignored.".format(stat_id, value))

						stat_strs.append(variation['string'].format(formatted_value))
						translated = True
						break

				if translated:
					break

			if not translated:
				raise Exception("Could not find suitable translation for stat '{}' with value '{}'.".format(stat_id, value))

		self._string = "\n".join(stat_strs)
		return self._string



	

'''
test_mods = """Sockets cannot be modified
+1 to Level of Socketed Gems
100% increased Global Defences
You can only Socket Corrupted Gems in this item
Zealot's Oath"""
'''

'''
FIXME: 

signage isn't done right for this mod, need to recognize that the value is negative
WARNING:root:'40% reduced Soul Cost of Vaal Skills' matches [u'vaal_skill_soul_cost_+%'] with values: ('40',)
'''



#print(parse(test_mods))

'''start = time.time()

test_mods = """100% increased Global Critical Strike Chance
75% increased Critical Strike Chance for Spells
40% reduced Soul Cost of Vaal Skills
Can have multiple Crafted Modifiers
78% increased Fire Damage
Adds 13 to 160 Lightning Damage to Spells
21% chance to Ignite"""

cs = combined_stats_t(test_mods, item=1)

logging.info(cs.dict())

logging.info(time.time()-start)'''