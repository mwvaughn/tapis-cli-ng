from tapis_cli.display import Verbosity
from .mixins import ActorIdentifier

from . import API_NAME, SERVICE_VERSION
from .formatters import ActorsFormatOne

__all__ = ['ActorsNoncesDelete']


class ActorsNoncesDelete(ActorsFormatOne, ActorIdentifier):
    """Delete a Nonce of an Actor
    """
    VERBOSITY = Verbosity.RECORD
    EXTRA_VERBOSITY = Verbosity.RECORD

    def get_parser(self, prog_name):
        parser = super(ActorsNoncesDelete, self).get_parser(prog_name)
        parser = ActorIdentifier.extend_parser(self, parser)
        parser.add_argument('nonceId',
                            metavar='<NONCE_ID>',
                            help='The id of the nonce to delete')
        return parser

    def take_action(self, parsed_args):
        parsed_args = self.preprocess_args(parsed_args)
        actor_id = ActorIdentifier.get_identifier(self, parsed_args)
        nonce_id = parsed_args.nonceId

        headers = ['deleted', 'messages']
        deleted = []
        messages = []

        try:
            self.tapis_client.actors.deleteNonce(actorId=actor_id,
                                                 nonceId=nonce_id)
            deleted.append(nonce_id)
        except Exception as err:
            messages.append(str(err))
        data = [deleted, messages]

        return (tuple(headers), tuple(data))
