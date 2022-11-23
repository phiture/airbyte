#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


from typing import Any, List, Mapping, Tuple

from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator

from .streams import (
    AggregateExportAdPartnerNameTotalCount,
    AggregateExportAdPartnerNameUniqueCount,
    AggregateExportAdsSetsTotalCount,
    AggregateExportAdsSetsUniqueCount,
    AggregateExportCampaignsTotalCount,
    AggregateExportCampaignsUniqueCount,
    AggregateExportCreativesTotalCount,
    AggregateExportCreativesUniqueCount,
    AggregateExportGeneralUserDimensionsTotalCount,
    AggregateExportGeneralUserDimensionsUniqueCount,
    AggregateExportKeywordTotalCount,
    AggregateExportKeywordUniqueCount,
    AggregateExportTouchTypeTotalCount,
    AggregateExportTouchTypeUniqueCount,
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
            AggregateExportAdPartnerNameTotalCount(authenticator=auth, config=config),
            AggregateExportAdPartnerNameUniqueCount(authenticator=auth, config=config),
            AggregateExportAdsSetsTotalCount(authenticator=auth, config=config),
            AggregateExportAdsSetsUniqueCount(authenticator=auth, config=config),
            AggregateExportCampaignsTotalCount(authenticator=auth, config=config),
            AggregateExportCampaignsUniqueCount(authenticator=auth, config=config),
            AggregateExportCreativesTotalCount(authenticator=auth, config=config),
            AggregateExportCreativesUniqueCount(authenticator=auth, config=config),
            AggregateExportGeneralUserDimensionsTotalCount(authenticator=auth, config=config),
            AggregateExportGeneralUserDimensionsUniqueCount(authenticator=auth, config=config),
            AggregateExportKeywordTotalCount(authenticator=auth, config=config),
            AggregateExportKeywordUniqueCount(authenticator=auth, config=config),
            AggregateExportTouchTypeTotalCount(authenticator=auth, config=config),
            AggregateExportTouchTypeUniqueCount(authenticator=auth, config=config),
        ]
