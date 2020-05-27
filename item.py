import logging

# 3rd Party

# Self
from item_base import item_t
import item_cluster_jewel
from profile_tools import profile_cumulative, profile, ChunkProfiler

def init():
	item_cluster_jewel.init()

def make_item(build, item_xml):
	base = item_t.get_base(item_xml)
	
	if base in item_cluster_jewel.bases:
		with ChunkProfiler('make_item-1'):
			return item_cluster_jewel.cluster_jewel_t(build, item_xml)
	else:
		with ChunkProfiler('make_item-2'):
			return item_t(build, item_xml)