
class PoBBotException(Exception):
	pass

class PastebinLimitException(PoBBotException):
	pass
	
class EligibilityException(PoBBotException):
	pass
	
# Thrown when creating a support gem that does not have gem data in data/support_gems.tsv
class GemDataException(PoBBotException):
	pass
	
class UnsupportedException(EligibilityException):
	pass