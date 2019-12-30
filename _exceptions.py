
class PoBBotException(Exception):
	pass

class ImporterLimitException(PoBBotException):
	pass
	
class EligibilityException(PoBBotException):
	pass
	
# Thrown when checking whether a support gem is supporting an active skill gem, but no support gem data with that name exists.
class GemDataException(PoBBotException):
	pass
	
class UnsupportedException(EligibilityException):
	pass
	
class PoBPartyException(PoBBotException):
	pass

class StatWhitelistException(PoBBotException):
	pass