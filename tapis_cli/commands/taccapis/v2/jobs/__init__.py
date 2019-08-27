"""Jobs service commands
"""
from .. import SERVICE_VERSION
from .job import Job, API_NAME
from .show import JobsShow
from .list import JobsList
from .search import JobsSearch
# now, aliased to JobsList
from .status import JobsStatus
# from .history import JobsHistory
