#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from datetime import date, datetime
from typing import Any, List, Mapping, Tuple

from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http.auth import TokenAuthenticator
from source_phiture_adjust.streams import ReportService


class SourcePhitureAdjust(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """
        See https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/source.py#L232
        for an example.

        :param config:  the user-input config object conforming to the connector's spec.yaml
        :param logger:  logger object
        :return Tuple[bool, any]: (True, None) if the input config can be used to connect to the API successfully, (False, error) otherwise.
        """
        date_before = date(2020, 1, 1)

        input_start_date = datetime.strptime(config["start_date"], "%Y-%m-%d").date()
        if input_start_date < date_before:
            return False, "Start date must be after 2020-01-01"

        if config.get("end_date"):
            input_end_date = datetime.strptime(config["end_date"], "%Y-%m-%d").date()
            if input_end_date < date_before:
                return False, "End date must be after 2020-01-01"

            if input_start_date > input_end_date:
                return False, "Start date must be before end date"

        return True, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        Define your streams here.

        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        auth_report_service = TokenAuthenticator(token=config["user_token"])
        return [ReportService(authenticator=auth_report_service, config=config)]
