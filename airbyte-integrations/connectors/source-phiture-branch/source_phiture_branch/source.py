#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from typing import Any, List, Mapping, Tuple

from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator

from .streams import (
    AggregateExportDownload_1,
    AggregateExportDownload_2,
    AggregateExportDownload_4,
    AggregateExportDownload_5,
    AggregateExportDownload_6,
    AggregateExportDownload_3,
    AggregateExportDownload_7,
)


class SourcePhitureBranch(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """
        See https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/source.py#L232
        for an example.

        :param config:  the user-input config object conforming to the connector's spec.yaml
        :param logger:  logger object
        :return Tuple[bool, any]: (True, None) if the input config can be used to connect to the API successfully, (False, error) otherwise.
        """
        if "skadnetwork-valid-messages" in config["data_sources"] and "total_count" not in config["aggregations"]:
            return False, "total_count must be selected when skadnetwork-valid-messages is selected"
        return True, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        Define your steams here.

        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        auth = TokenAuthenticator(token=config["api_key"], auth_method="", auth_header="Access-Token")
        return [
            AggregateExportDownload_1(authenticator=auth, config=config),
            AggregateExportDownload_2(authenticator=auth, config=config),
            AggregateExportDownload_3(authenticator=auth, config=config),
            AggregateExportDownload_4(authenticator=auth, config=config),
            AggregateExportDownload_5(authenticator=auth, config=config),
            AggregateExportDownload_6(authenticator=auth, config=config),
            AggregateExportDownload_7(authenticator=auth, config=config),
        ]
