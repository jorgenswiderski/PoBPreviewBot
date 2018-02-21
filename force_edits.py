from util import parse_time_str
from util import calc_deletion_check_time
import time

def main(time_str, dcl):
	sec = parse_time_str(time_str)
	
	dct = calc_deletion_check_time(None, comment_age=sec)
	
	threshold = time.time() + dct
	
	for entry in dcl:
		if int(entry['time']) < threshold:
			print "Flagging {} for update.".format(entry['id'])
			entry['time'] = 0
	
	return dcl