import logging

# 3rd Party

# Self
from item_base import item_t
import item_cluster_jewel

def init():
	item_cluster_jewel.init()

def make_item(build, item_xml):
	item = item_t(build, item_xml)

	# FIXME: Calls constructor twice in some cases, because
	# I'm using item_t.__parse_xml__() to determine the base type

	if item.base in ["Large Cluster Jewel", "Medium Cluster Jewel", "Small Cluster Jewel"]:
		return item_cluster_jewel.cluster_jewel_t(build, item_xml)

	return item