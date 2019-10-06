# Python
import logging
import json
from hashlib import md5

# 3rd Party
import requests
from atomicwrites import atomic_write

# Self
from _exceptions import PoBPartyException

endpoint = "https://pob.party/kv/put?ver={}"
# ex: https://pob.party/kv/put?ver=v3.6.0
# ex: https://pob.party/kv/put?ver=latest

headers = {
	'content-type': 'text/plain',
}

path = 'save/pob_party.json'

try:
	with open(path, 'r') as f:
		hashmap = json.load(f)
except IOError:
	hashmap = {}
	pass

def get_url(pastebin):
	hash = md5(pastebin.contents()).hexdigest()
	
	if hash not in hashmap:
		# FIXME: Figure out proper way to determine the version number
		r = requests.post(endpoint.format('latest'), data=pastebin.contents(), headers=headers)
		
		if r.status_code != 200:
			raise PoBPartyException('Request failed: {}'.format(r.status_code))
		
		rj = r.json()
		
		if 'url' not in rj:
			raise PoBPartyException('Response json did not contain URL token.')
		
		logging.debug("{}'s pob.party token is {}.".format(pastebin, rj['url']))
		
		hashmap[hash] = rj['url']
		
		with atomic_write(path, overwrite=True) as f:
			json.dump(hashmap, f, sort_keys=True, indent=4)
		
	return "https://pob.party/share/{}".format(hashmap[hash])

def set_key(pobparty):
	hash = md5(pobparty.contents()).hexdigest()

	if hash not in hashmap:
		hashmap[hash] = pobparty.key.lower()