# Python
import logging
import logging.handlers
import sys

# 3rd Party
# Self

class ThirdPartyFilter(logging.Filter):
	def __init__(self, names):
		logging.Filter.__init__(self)
		
		self.names = names

	def filter(self, record):
		if (record.name in self.names and record.levelno == logging.DEBUG):
			return False
			
		return True

def create_console_handler():
	h = logging.StreamHandler(stream=sys.stdout)
	h.setFormatter(logging.Formatter(
		fmt='%(asctime)s> %(message)s',
		datefmt='%Y/%m/%d %H:%M:%S'
	))
	h.setLevel(logging.INFO)
	'''
	h.addFilter(ThirdPartyFilter([
		'prawcore',
		'urllib3.connectionpool'
	]))
	'''
	logging.getLogger().addHandler(h)

def create_log_handler():
	h = logging.handlers.TimedRotatingFileHandler('logs/log', when='midnight', backupCount=30)
	h.setFormatter(format)
	h.setLevel(logging.INFO)
	
	logging.getLogger().addHandler(h)

def create_debug_handler():
	h = logging.handlers.TimedRotatingFileHandler('logs/debug', when='h', backupCount=48)
	h.setFormatter(format)
	h.setLevel(logging.DEBUG)
	
	h.addFilter(ThirdPartyFilter([
		'prawcore',
		'urllib3.connectionpool'
	]))
	
	logging.getLogger().addHandler(h)

def init_logging():
	log = logging.getLogger()
	log.setLevel(logging.DEBUG)
	# Remove the default handler
	log.removeHandler(log.handlers[0])
	
	#print(len(log.handlers))

	global format
	format = logging.Formatter(
		fmt='%(asctime)s %(levelname)s %(filename)s:%(lineno)d> %(message)s',
		datefmt='%Y/%m/%d %H:%M:%S'
	)
	
	create_console_handler()
	create_log_handler()
	create_debug_handler()