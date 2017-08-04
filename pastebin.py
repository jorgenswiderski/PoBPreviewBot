import urllib2
import re
import base64
import zlib
import defusedxml.ElementTree as ET
	
def decode_base64_and_inflate( b64string ):
	decoded_data = base64.b64decode( b64string )
	try:
		return zlib.decompress( decoded_data )
	except zlib.error:
		pass

def strip_url_to_key(url):
	match = re.search('\w+$', url)
	paste_key = match.group(0)
	return paste_key
	
def get_contents(paste_key):
	raw_url = 'https://pastebin.com/raw/' + paste_key
	
	data = urllib2.urlopen(raw_url).read()
	return data
	
def decode_to_xml(enc):
	enc = enc.replace("-", "+").replace("_", "/")
	
	xml_str = decode_base64_and_inflate(enc)
	
	xml = ET.fromstring(xml_str)
	
	return xml
	
def get_as_xml(paste_key):
	contents = get_contents(paste_key)
	return decode_to_xml(contents)