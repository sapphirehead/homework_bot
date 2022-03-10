class CustomStatusError(Exception):
    """Custom exception if http-status is not equal 200."""


class CustomNotListError(Exception):
    """Custom exception if response is not equal to list type."""


class CustomTokenError(Exception):
    """Custom exception if any token is not exist"""


class CustomEmptyListError(Exception):
    """Custom exception if list with homeworks is empty"""


class CustomAPINotAccessError(Exception):
    """If the endpoint is not reachable."""
