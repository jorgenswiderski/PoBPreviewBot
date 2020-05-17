import logging

# 3rd Party

# Self
from item_base import item_t
from item_cluster_jewel import cluster_jewel_t

def make_item(build, item_xml):
	item = item_t(build, item_xml)

	# FIXME: Calls constructor twice in some cases, because
	# I'm using item_t.__parse_xml__() to determine the base type

	if item.base in ["Large Cluster Jewel", "Medium Cluster Jewel", "Small Cluster Jewel"]:
		return cluster_jewel_t(build, item_xml)

	return item