# Python
import logging
import json
from hashlib import md5

# 3rd Party
import requests

# Self
from _exceptions import PoBPartyException

endpoint = "https://pob.party/kv/put?ver=v{}"
# ex: https://pob.party/kv/put?ver=v3.6.0

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
		r = requests.post(endpoint.format('3.6.0'), data=pastebin.contents(), headers=headers)
		
		if r.status_code != 200:
			raise PoBPartyException('Request failed: {}'.format(r.status_code))
		
		rj = r.json()
		
		if 'url' not in rj:
			raise PoBPartyException('Response json did not contain URL token.')
		
		logging.debug("{}'s pob.party token is {}.".format(pastebin, rj['url']))
		
		hashmap[hash] = rj['url']
		
		with open(path, 'w') as f:
			json.dump(hashmap, f, sort_keys=True, indent=4)
		
	return "https://pob.party/share/{}".format(hashmap[hash])