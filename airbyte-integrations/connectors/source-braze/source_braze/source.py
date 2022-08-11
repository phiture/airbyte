#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from typing import Any, List, Mapping, Tuple

from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http.auth import TokenAuthenticator

from source_braze.streams_campaigns import CampaignsList, CampaignsDetails, CampaignsDataSeries
from source_braze.streams_canvas import CanvasList, CanvasDetails, CanvasDataSeries


class SourceBraze(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """
        See https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/source.py#L232
        for an example.

        :param config:  the user-input config object conforming to the connector's spec.yaml
        :param logger:  logger object
        :return Tuple[bool, any]: (True, None) if the input config can be used to connect to the API successfully, (False, error) otherwise.
        """
        return True, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        Define your streams here.

        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        auth = TokenAuthenticator(token=config['api_key'])
        return [
            CampaignsList(authenticator=auth, config=config),
            CampaignsDetails(authenticator=auth, config=config),
            CampaignsDataSeries(authenticator=auth, config=config),
            CanvasList(authenticator=auth, config=config),
            CanvasDetails(authenticator=auth, config=config),
            CanvasDataSeries(authenticator=auth, config=config)
        ]
