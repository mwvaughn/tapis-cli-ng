from tapis_cli.display import Verbosity
from tapis_cli.search import SearchWebParam
from tapis_cli.utils import fnmatches

from . import API_NAME, SERVICE_VERSION
from .formatters import ActorsFormatMany
from .mixins import ActorIdentifier
from .models import Worker
from .mixins import GlobListFilter

__all__ = ['ActorsWorkersList']


class ActorsWorkersList(ActorsFormatMany, ActorIdentifier, GlobListFilter):
    """List the Workers for a specific Actor
    """
    VERBOSITY = Verbosity.RECORD
    EXTRA_VERBOSITY = Verbosity.RECORD_VERBOSE
    FILTERABLE_KEYS = Worker.FILTERABLE_KEYS

    def get_parser(self, prog_name):
        parser = super(ActorsWorkersList, self).get_parser(prog_name)
        parser = ActorIdentifier.extend_parser(self, parser)
        parser = GlobListFilter.extend_parser(self, parser)
        return parser

    def take_action(self, parsed_args):
        parsed_args = self.preprocess_args(parsed_args)
        actor_id = ActorIdentifier.get_identifier(self, parsed_args)
        results = self.tapis_client.actors.listWorkers(actorId=actor_id)
        headers = ["workerId", "status"]
        records = []
        for rec in results:

            include = False
            if parsed_args.list_filter is None:
                include = True
            else:
                for k in self.FILTERABLE_KEYS:
                    if parsed_args.list_filter in rec[k]:
                        include = True
                    elif fnmatches(rec[k], [parsed_args.list_filter]):
                        include = True

            if include:
                record = []
                record.append(rec.get('id'))
                record.append(rec.get('status'))
                if record not in records:
                    records.append(record)

        return (tuple(headers), tuple(records))
