#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from typing import Any, Iterable, Mapping, MutableMapping, Optional, List

import pendulum
import requests
from airbyte_cdk.models import SyncMode

from source_adjust.streams import AdjustStream
from source_adjust.util_report_service import dimensions, metrics, custom_metrics


class ReportService(AdjustStream):
    url_base = "https://dash.adjust.com"

    primary_key = dimensions
    cursor_field = "day"
    time_interval = {"days": 1}
    state_checkpoint_interval = 1000

    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(**kwargs)
        self._app_token = config['app_token']
        self._start_date = config['start_date']
        self._end_date = config.get('end_date')
        self._attribution_type = config.get('attribution_type')
        self._ad_spend_mode = config.get('ad_spend_mode')
        self._currency = config.get('currency')
        self._custom_metrics = config.get('custom_metrics')
        self._state = {}

    @property
    def state(self) -> MutableMapping[str, Any]:
        return self._state

    @state.setter
    def state(self, value: MutableMapping[str, Any]):
        self._state.update(value)

    def current_state(self, canvas_id, default=None):
        default = default or self.state.get(self.cursor_field)
        return self.state.get(canvas_id, {}).get(self.cursor_field) or default

    def path(
            self,
            stream_state: Mapping[str, Any] = None,
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "control-center/reports-service/report"

    def request_params(
            self,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        all_metrics = ",".join(metrics)
        if self._custom_metrics:
            all_metrics += f",{self._custom_metrics}"
        if custom_metrics:
            all_metrics += f",{custom_metrics}"
        return {
            "app_token__in": self._app_token,
            "date_period": f'{stream_slice["start_date"]}:{stream_slice["end_date"]}',
            "dimensions": ",".join(dimensions),
            "metrics": ",".join(metrics),
            "attribution_type": self._attribution_type,
            "ad_spend_mode": self._ad_spend_mode,
            "currency": self._currency,
        }

    def parse_response(
            self,
            response: requests.Response,
            stream_state: Mapping[str, Any],
            stream_slice: Mapping[str, Any] = None,
            next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        data = response.json()
        for row in data['rows']:
            yield row

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

    def read_records(
            self, sync_mode: SyncMode, cursor_field: List[str] = None, stream_slice: MutableMapping[str, Any] = None, **kwargs
    ) -> Iterable[Mapping[str, Any]]:
        for record in super().read_records(sync_mode=sync_mode, stream_slice=stream_slice):
            current_state = self.current_state(self._app_token)
            if current_state:
                date_in_current_stream = pendulum.parse(current_state)
                date_in_latest_record = pendulum.parse(record[self.cursor_field])
                cursor_value = (max(date_in_current_stream, date_in_latest_record)).to_date_string()
                self.state = {self._app_token: {self.cursor_field: cursor_value}}
                yield record
                continue
            self.state = {self._app_token: {self.cursor_field: record[self.cursor_field]}}
            yield record
