import re
import logging
import math

# 3rd Party
import defusedxml.ElementTree as ET

# Self
import util
import logger
import stat_parsing

# Base Item Class

class item_t(object):
	re_implicits = re.compile("^Implicits: \d+")
	re_any_curly_tag = re.compile("{.+}")
	re_range = re.compile("\{range:(\d+\.?\d*)\}")
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
		mods = []

		done_skipping_through_garbage = False

		for i in range(0, len(rows)):
			if self.re_implicits.search(rows[i]):
				done_skipping_through_garbage = True
				continue

			if not done_skipping_through_garbage:
				continue
				
			# check if the mod is for an inactive variant
			if not self.is_mod_active(rows[i]):
				continue

			# process range tags and convert range to a number
			range_match = self.re_range.search(rows[i])

			if range_match:
				range_value = float(range_match.group(1))
				bounds = re.search("\((\d+\.?\d*)\-(\d+\.?\d*)\)", rows[i])

				if not bounds:
					logging.debug("could not find ranges when parsing range mod. row={} item={} id={} mod={}".format(i, self.name, self.id, rows[i]))
				else:
					range_min = float(bounds.group(1))
					range_max = float(bounds.group(2))
					range_delta = range_max - range_min

					places = 0

					if math.ceil(range_min) != range_min:
						p_match = re.search("\.(.+)", bounds.group(1))

						if not p_match:
							raise ValueError("{} {}".format(rows[i], bounds.group(1)))

						places = len(p_match.group(1))

					factor = 10 ^ places

					final_value = math.ceil( (range_min + range_delta * range_value) * factor) / factor

					format_str = "{:." + str(places) + "f}"

					new_row = re.sub("\(\d+\.?\d*\-\d+\.?\d*\)", format_str.format(final_value), rows[i], count=1)

					logging.log(logger.DEBUG_ALL, "{} ==> {}".format(rows[i], new_row))

					rows[i] = new_row

			# trim out the curly bracketed tags
			replaced = self.re_any_curly_tag.sub("", rows[i])

			# skip empty lines
			if len(replaced.strip()) <= 0:
				continue

			mods.append(replaced)

		self.stats = stat_parsing.combined_stats_t("\n".join(mods), item=self)
		logging.log(logger.DEBUG_ALL, self.stats.dict())
		
	def __parse_for_support_gems__(self):
		self.support_mods = {}

		for id, value in self.stats.dict().items():
			if id in stat_parsing.support_gem_map:
				for granted_effect in stat_parsing.support_gem_map[id]:
					data = gem_t.get_gem_data(id=granted_effect)
					
					if data:
						self.support_mods[data.id] = data
						logging.log(logger.DEBUG_ALL, "{} registered as support granted by {}.".format(granted_effect, self.name))
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