#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from typing import Any, List, Mapping, Tuple

import pendulum
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream

from .streams import GetReportsReportAdGroup


# Source
class SourcePhitureSearchads(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        """
        See https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/source.py#L232
        for an example.

        :param config:  the user-input config object conforming to the connector's spec.yaml
        :param logger:  logger object
        :return Tuple[bool, any]: (True, None) if the input config can be used to connect to the API successfully, (False, error) otherwise.
        """
        date_before = pendulum.parse("2020-01-01")

        input_start_date = pendulum.parse(config["start_date"])
        if input_start_date < date_before:
            return False, "Start date must be after 2020-01-01"

        if config.get("end_date"):
            input_end_date = pendulum.parse(config["end_date"])
            if input_end_date < date_before:
                return False, "End date must be after 2020-01-01"

            if input_start_date > input_end_date:
                return False, "Start date must be before end date"

        if config.get('goals_ids'):
            goals_ids = config.get('goals_ids').split(',')
            for goal_id in goals_ids:
                if not goal_id.isdigit():
                    return False, "Goal IDs must be integers"

        return True, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        """
        :param config: A Mapping of the user input configuration as defined in the connector spec.
        """
        return [GetReportsReportAdGroup(config=config)]
