import datetime
import getpass
import json
import logging
import petname
import sys
import agavepy
from agavepy.agave import Agave, AgaveError
from agavepy import tenants
from requests.exceptions import HTTPError
from tapis_cli.display import Verbosity
from tapis_cli.constants import PLATFORM, TAPIS_AUTH_FAIL
from tapis_cli.utils import (fmtcols, prompt, get_hostname, get_public_ip,
                             get_local_username)
from tapis_cli.settings import TAPIS_DEFAULT_TENANT_ID, TAPIS_CLI_VERIFY_SSL
from tapis_cli import et
from tapis_cli.firstrun import firstrun

from . import API_NAME, SERVICE_VERSION
from .models import Token
from .formatters import CreateTokenFormatOne
from . import gitserver, registry

from .gitserver.init import GitServerOpts
from .registry.init import RegistryOpts

__all__ = ['AuthInit']

logging.getLogger(__name__).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

CLIENT_PREFIX = '_cli'


class AuthInit(CreateTokenFormatOne, RegistryOpts, GitServerOpts):
    """Configure the local host for use with Tapis
    """
    VERBOSITY = Verbosity.BRIEF
    EXTRA_VERBOSITY = Verbosity.RECORD_VERBOSE

    def get_parser(self, prog_name):
        parser = super(AuthInit, self).get_parser(prog_name)
        # TODO - Cowboy these in here now until the init workflow is solidified

        t = parser.add_mutually_exclusive_group()
        t.add_argument('--tenant-id',
                       dest='tenant_id',
                       help='{0} tenant ID'.format(PLATFORM))
        t.add_argument('--api-server',
                       dest='api_server',
                       help='{0} API server'.format(PLATFORM))

        parser.add_argument('--username',
                            dest='username',
                            help='{0} username'.format(PLATFORM))
        parser.add_argument('--password',
                            dest='password',
                            help='{0} password'.format(PLATFORM))

        parser = RegistryOpts.extend_parser(parser)
        parser = GitServerOpts.extend_parser(parser)

        parser.add_argument('--interactive',
                            action='store_true',
                            help='Prompt for all values')

        parser.add_argument('--quiet',
                            action='store_false',
                            help='Do not display configuration after run')
        return parser

    # TODO - refactor to be have lower code complexity
    def take_action(self, parsed_args):
        # Load what we can from credentials cache. Ultimately, if no
        # overrides are specified, the cached contents will be used to
        # populate the Tapis client.

        firstrun()

        if parsed_args.interactive:
            print('Configure Tapis API access:')
            print('##########################')

        try:
            logger.debug('Read from local Tapis cache...')
            ag_context = Agave._read_current(agave_kwargs=True)
        except FileNotFoundError:
            # A very common case (all new tapis_cli installs, for instance), will
            # find NO cache file on disk. This must be recoverable, so set the
            # context to an empty dict
            ag_context = {}

        # Inject a password field (which may be filled later) into the context
        ag_context['password'] = None

        # Process overrides to ag_context provided by parsed_args
        mandate_username = False
        mandate_password = False

        # Process tenant override
        parsed_tenant_id = getattr(parsed_args, 'tapis_tenant_id', None)
        if parsed_tenant_id is not None:
            if ag_context.get('tenant_id', None) != parsed_tenant_id:
                mandate_username = True
                mandate_password = True
                logger.warning(
                    'Tenant changed. Username and password must be specified.')
            ag_context['tenant_id'] = parsed_tenant_id

        # Process username override
        parsed_username = getattr(parsed_args, 'tapis_username', None)
        if parsed_username is not None:
            if ag_context.get('username', None) != parsed_username:
                mandate_password = True
                logger.warning('Username changed. Password must be specified.')
            ag_context['username'] = parsed_username

        # If interactive OR cannot establish tenant_id, prompt for it
        temp_tenant_id = ag_context.get('tenant_id', None)
        if temp_tenant_id is None or parsed_args.interactive:
            if temp_tenant_id is None:
                temp_tenant_id = TAPIS_DEFAULT_TENANT_ID
            tl = [t.get('code') for t in agavepy.tenants.list_tenants()]
            print('Available Tenants')
            print('*****************')
            print(fmtcols(tl, 5))
            ag_context['tenant_id'] = prompt('Enter a tenant name',
                                             temp_tenant_id)

        ag_context['api_server'] = agavepy.tenants.api_server_by_id(
            ag_context['tenant_id'])

        # Prompt when interactive or username is reset or unavailable
        if mandate_username or ag_context.get(
                'username', None) is None or parsed_args.interactive:
            mandate_password = True
            ag_context['username'] = prompt('Username',
                                            ag_context.get('username', None))

        # Set client name now that we have tenant and user
        ag_context['client_name'] = '{0}-{1}-{2}-{3}'.format(
            CLIENT_PREFIX, ag_context['tenant_id'], ag_context['username'],
            get_hostname())

        # Prompt when interactive or tenant/username is reset or unavailable
        if mandate_password or parsed_args.interactive:
            temp_password = getattr(parsed_args, 'tapis_password', None)
            if temp_password is None or parsed_args.interactive:
                temp_password = prompt('Password for {0}'.format(
                    ag_context['username']),
                                       temp_password,
                                       secret=True)

            # Remove extant api_key, api_secret, and tokens to ensure the
            # HTTP Basic Auth processor will be loaded when the context is
            # sent to an Agave instance.
            ag_context['password'] = temp_password
            ag_context['api_key'] = None
            ag_context['api_secret'] = None
            ag_context['access_token'] = None
            ag_context['refresh_token'] = None

        api_key = ag_context.get('api_key', None)
        ag = None

        # No client was loadable from the local system
        if api_key is None or api_key == '':
            logger.debug('clients.create: {0}'.format(
                ag_context['client_name']))
            create_context = {
                'api_server': ag_context['api_server'],
                'username': ag_context['username'],
                'password': ag_context['password'],
                'verify': TAPIS_CLI_VERIFY_SSL
            }
            ag = Agave(**create_context)

            # Preflight activity: Get rid of existing client
            try:
                logger.debug('clients.delete()...')
                ag.clients.delete(clientName=ag_context['client_name'])
            except Exception:
                logger.debug('Client was not deleted')
                pass

            logger.info('clients.create: {0}'.format(
                ag_context['client_name']))
            try:
                ag.clients.create(
                    body={
                        'clientName':
                        ag_context['client_name'],
                        'description':
                        'Generated by {0}@{1} at {2}'.format(
                            get_local_username(), get_public_ip(),
                            datetime.datetime.utcnow().strftime(
                                "%Y-%m-%dT%H:%M:%SZ"))
                    })
            except Exception as err:
                # logger.error('{0} client was not created: Exiting.'.format(PLATFORM))
                raise AgaveError(
                    'Tapis client was not created: {0}'.format(err))
        else:
            # Client was cached - load it up
            logger.debug('Loading client from cache...')
            ag = Agave(**ag_context)

        # Hit profiles service to check client
        try:
            ag.profiles.get()
        except Exception as err:
            logger.error('Tapis client is not active...')
            raise AgaveError(TAPIS_AUTH_FAIL)

        # Formulate a table view of key values for current session
        headers = [
            'tenant_id', 'username', 'client_name', 'api_key', 'access_token',
            'expires_at', 'verify'
        ]
        data = [
            # Coerce to string to avoid failures where a deepcopy
            # operation in Python's implementation of tuple() is
            # unable to accomodate copying properties of an Agave object
            str(ag.tenant_id),
            str(ag.username),
            str(ag_context['client_name']),
            str(ag.api_key),
            str(ag._token),
            str(ag.expires_at),
            str(ag.verify)
        ]

        (headers, data) = registry.init.interactive(parsed_args, headers, data)
        (headers, data) = gitserver.init.interactive(parsed_args, headers,
                                                     data)

        et.phone_home()
        # if parsed_args.quiet:
        #     return (tuple(), tuple())
        # else:
        #     return (tuple(headers), tuple(data))

        return (tuple(headers), tuple(data))
