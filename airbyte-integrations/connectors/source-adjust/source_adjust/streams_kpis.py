#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from typing import Any, Iterable, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode

from source_adjust.streams import AdjustStream
from source_adjust.util_kpis import all_kpis_joined_by_comma, events_kpis_joined_by_pipeline


class Kpis(AdjustStream):
    primary_key = None
    cursor_field = "date"
    time_interval = {"days": 1}

    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(**kwargs)
        self._app_token = config['app_token']
        self._start_date = config['start_date']
        self._end_date = config.get('end_date')

    def path(
            self,
            stream_state: Mapping[str, Any] = None,
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None
    ) -> str:
        return f"kpis/v1/{self._app_token}.json"

    def request_params(
            self,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "start_date": stream_slice["start_date"],
            "end_date": stream_slice["end_date"],
            "grouping": "trackers,countries",
            "kpis": all_kpis_joined_by_comma,
            "event_kpis": "all_" + events_kpis_joined_by_pipeline,
        }

    def parse_response(
            self,
            response: requests.Response,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        return [response.json()]

    def stream_slices(self, sync_mode: SyncMode, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        stream_state = stream_state or {}

        if stream_state.get('last_sync'):
            start_date = pendulum.parse(stream_state['last_sync'].get(self.cursor_field))
        else:
            start_date = pendulum.parse(self._start_date)

        end_date = pendulum.parse(self._end_date or pendulum.now().to_date_string())

        while start_date <= end_date and start_date < pendulum.parse(pendulum.now().to_date_string()):
            starting_at = start_date
            ending_at = start_date

            self.logger.info(
                f"Fetching {self.name} ; time range: {starting_at.to_date_string()} - {ending_at.to_date_string()}"
            )

            yield {
                "start_date": starting_at.to_date_string(),
                "end_date": ending_at.to_date_string(),
            }
            start_date = start_date.add(**self.time_interval)
