#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from typing import Any, List, Mapping, Tuple

from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from .streams import (
    PostQueryInstallTotalCount,
    PostQueryReInstallTotalCount,
    PostQueryClickTotalCount,
    PostQueryOpenTotalCount,
    PostQueryImpressionTotalCount,
    PostQueryCustomEventTotalCount,
    PostQueryInstallUniqueCount,
    PostQueryReInstallUniqueCount,
    PostQueryClickUniqueCount,
    PostQueryOpenUniqueCount,
    PostQueryImpressionUniqueCount,
    PostQueryCustomEventUniqueCount,
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
        return True, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        Define your steams here.

        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        return [
            PostQueryInstallTotalCount(config=config),
            PostQueryReInstallTotalCount(config=config),
            PostQueryClickTotalCount(config=config),
            PostQueryOpenTotalCount(config=config),
            PostQueryImpressionTotalCount(config=config),
            PostQueryCustomEventTotalCount(config=config),
            PostQueryInstallUniqueCount(config=config),
            PostQueryReInstallUniqueCount(config=config),
            PostQueryClickUniqueCount(config=config),
            PostQueryOpenUniqueCount(config=config),
            PostQueryImpressionUniqueCount(config=config),
            PostQueryCustomEventUniqueCount(config=config),
        ]
